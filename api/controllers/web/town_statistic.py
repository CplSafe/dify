"""Anonymous, aggregate-only town statistics for published WebApps."""

from datetime import datetime

import sqlalchemy as sa
from flask import abort, jsonify, request
from flask_restx import Resource
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from werkzeug.exceptions import Forbidden, NotFound

from constants import HEADER_NAME_APP_CODE
from controllers.common.schema import register_schema_models
from controllers.web import web_ns
from core.app.entities.app_invoke_entities import InvokeFrom
from extensions.ext_database import db
from libs.datetime_utils import parse_time_range
from libs.helper import convert_datetime_to_date
from models.model import App, Site

PUBLIC_STATS_TIMEZONE = "Asia/Shanghai"


class TownStatisticTimeRangeQuery(BaseModel):
    start: str | None = Field(default=None, description="Start date (YYYY-MM-DD HH:MM)")
    end: str | None = Field(default=None, description="End date (YYYY-MM-DD HH:MM)")

    @field_validator("start", "end", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: str | None) -> str | None:
        return value or None


register_schema_models(web_ns, TownStatisticTimeRangeQuery)


def _get_public_app() -> App:
    app_code = request.headers.get(HEADER_NAME_APP_CODE)
    if not app_code:
        raise NotFound()

    site = db.session.scalar(select(Site).where(Site.code == app_code, Site.status == "normal").limit(1))
    if not site:
        raise NotFound()

    app = db.session.get(App, site.app_id)
    if not app:
        raise NotFound()
    if not app.enable_site:
        raise Forbidden()
    return app


def _parse_range() -> tuple[datetime | None, datetime | None]:
    args = TownStatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))
    try:
        return parse_time_range(args.start, args.end, PUBLIC_STATS_TIMEZONE)
    except ValueError as error:
        abort(400, description=str(error))


@web_ns.route("/town-statistics/distribution")
class PublicTownDistributionStatistic(Resource):
    """Return aggregate conversation and end-user counts grouped by town."""

    def get(self):
        app = _get_public_app()
        start_datetime_utc, end_datetime_utc = _parse_range()
        sql_query = """SELECT
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') AS town,
    COUNT(*) AS conversation_count,
    COUNT(DISTINCT from_end_user_id) AS user_count
FROM conversations
WHERE app_id = :app_id
    AND is_deleted IS false
    AND (invoke_from IS NULL OR invoke_from != :invoke_from)"""
        village_sql_query = """SELECT
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') AS town,
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 2), '') AS village,
    COUNT(*) AS conversation_count,
    COUNT(DISTINCT from_end_user_id) AS user_count
FROM conversations
WHERE app_id = :app_id
    AND is_deleted IS false
    AND (invoke_from IS NULL OR invoke_from != :invoke_from)
    AND NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') IS NOT NULL
    AND NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 2), '') IS NOT NULL"""
        args = {"app_id": app.id, "invoke_from": InvokeFrom.DEBUGGER}
        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            village_sql_query += " AND created_at >= :start"
            args["start"] = start_datetime_utc
        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            village_sql_query += " AND created_at < :end"
            args["end"] = end_datetime_utc
        sql_query += " GROUP BY town ORDER BY conversation_count DESC, town"
        village_sql_query += " GROUP BY town, village ORDER BY conversation_count DESC, town, village"

        data = []
        village_data = []
        unspecified_count = 0
        unspecified_user_count = 0
        with db.engine.begin() as connection:
            rows = connection.execute(sa.text(sql_query), args)
            for row in rows:
                if row.town is None:
                    unspecified_count = row.conversation_count
                    unspecified_user_count = row.user_count
                else:
                    data.append(
                        {
                            "town": row.town,
                            "conversation_count": row.conversation_count,
                            "user_count": row.user_count,
                        }
                    )
            village_rows = connection.execute(sa.text(village_sql_query), args)
            for row in village_rows:
                village_data.append(
                    {
                        "town": row.town,
                        "village": row.village,
                        "conversation_count": row.conversation_count,
                        "user_count": row.user_count,
                    }
                )

        return jsonify(
            {
                "data": data,
                "villages": village_data,
                "unspecified_count": unspecified_count,
                "unspecified_user_count": unspecified_user_count,
            }
        )


@web_ns.route("/town-statistics/trend")
class PublicTownTrendStatistic(Resource):
    """Return daily aggregate conversation counts grouped by town."""

    def get(self):
        app = _get_public_app()
        start_datetime_utc, end_datetime_utc = _parse_range()
        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') AS town,
    COUNT(*) AS conversation_count
FROM conversations
WHERE app_id = :app_id
    AND is_deleted IS false
    AND (invoke_from IS NULL OR invoke_from != :invoke_from)
    AND NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') IS NOT NULL"""
        village_sql_query = f"""SELECT
    {converted_created_at} AS date,
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') AS town,
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 2), '') AS village,
    COUNT(*) AS conversation_count
FROM conversations
WHERE app_id = :app_id
    AND is_deleted IS false
    AND (invoke_from IS NULL OR invoke_from != :invoke_from)
    AND NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') IS NOT NULL
    AND NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 2), '') IS NOT NULL"""
        args = {"tz": PUBLIC_STATS_TIMEZONE, "app_id": app.id, "invoke_from": InvokeFrom.DEBUGGER}
        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            village_sql_query += " AND created_at >= :start"
            args["start"] = start_datetime_utc
        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            village_sql_query += " AND created_at < :end"
            args["end"] = end_datetime_utc
        sql_query += " GROUP BY date, town ORDER BY date, town"
        village_sql_query += " GROUP BY date, town, village ORDER BY date, town, village"

        data = []
        village_data = []
        with db.engine.begin() as connection:
            rows = connection.execute(sa.text(sql_query), args)
            for row in rows:
                data.append(
                    {
                        "date": str(row.date),
                        "town": row.town,
                        "conversation_count": row.conversation_count,
                    }
                )
            village_rows = connection.execute(sa.text(village_sql_query), args)
            for row in village_rows:
                village_data.append(
                    {
                        "date": str(row.date),
                        "town": row.town,
                        "village": row.village,
                        "conversation_count": row.conversation_count,
                    }
                )
        return jsonify({"data": data, "villages": village_data})
