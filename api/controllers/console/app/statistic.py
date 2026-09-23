from decimal import Decimal

import sqlalchemy as sa
from flask import abort, jsonify, request
from flask_restx import Resource, fields
from pydantic import BaseModel, Field, field_validator

from controllers.console import console_ns
from controllers.console.app.wraps import get_app_model
from controllers.console.wraps import account_initialization_required, setup_required
from core.app.entities.app_invoke_entities import InvokeFrom
from extensions.ext_database import db
from libs.datetime_utils import parse_time_range
from libs.helper import convert_datetime_to_date
from libs.login import current_account_with_tenant, login_required
from models import AppMode

DEFAULT_REF_TEMPLATE_SWAGGER_2_0 = "#/definitions/{model}"


class StatisticTimeRangeQuery(BaseModel):
    start: str | None = Field(default=None, description="Start date (YYYY-MM-DD HH:MM)")
    end: str | None = Field(default=None, description="End date (YYYY-MM-DD HH:MM)")

    @field_validator("start", "end", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value


console_ns.schema_model(
    StatisticTimeRangeQuery.__name__,
    StatisticTimeRangeQuery.model_json_schema(ref_template=DEFAULT_REF_TEMPLATE_SWAGGER_2_0),
)


@console_ns.route("/apps/<uuid:app_id>/statistics/daily-messages")
class DailyMessageStatistic(Resource):
    @console_ns.doc("get_daily_message_statistics")
    @console_ns.doc(description="Get daily message statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Daily message statistics retrieved successfully",
        fields.List(fields.Raw(description="Daily message count data")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    COUNT(*) AS message_count
FROM
    messages
WHERE
    app_id = :app_id
    AND invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date ORDER BY date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({"date": str(i.date), "message_count": i.message_count})

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/daily-conversations")
class DailyConversationStatistic(Resource):
    @console_ns.doc("get_daily_conversation_statistics")
    @console_ns.doc(description="Get daily conversation statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Daily conversation statistics retrieved successfully",
        fields.List(fields.Raw(description="Daily conversation count data")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    COUNT(DISTINCT conversation_id) AS conversation_count
FROM
    messages
WHERE
    app_id = :app_id
    AND invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date ORDER BY date"

        response_data = []
        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({"date": str(i.date), "conversation_count": i.conversation_count})

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/daily-end-users")
class DailyTerminalsStatistic(Resource):
    @console_ns.doc("get_daily_terminals_statistics")
    @console_ns.doc(description="Get daily terminal/end-user statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Daily terminal statistics retrieved successfully",
        fields.List(fields.Raw(description="Daily terminal count data")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    COUNT(DISTINCT messages.from_end_user_id) AS terminal_count
FROM
    messages
WHERE
    app_id = :app_id
    AND invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date ORDER BY date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({"date": str(i.date), "terminal_count": i.terminal_count})

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/token-costs")
class DailyTokenCostStatistic(Resource):
    @console_ns.doc("get_daily_token_cost_statistics")
    @console_ns.doc(description="Get daily token cost statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Daily token cost statistics retrieved successfully",
        fields.List(fields.Raw(description="Daily token cost data")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    (SUM(messages.message_tokens) + SUM(messages.answer_tokens)) AS token_count,
    SUM(total_price) AS total_price
FROM
    messages
WHERE
    app_id = :app_id
    AND invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date ORDER BY date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append(
                    {"date": str(i.date), "token_count": i.token_count, "total_price": i.total_price, "currency": "USD"}
                )

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/average-session-interactions")
class AverageSessionInteractionStatistic(Resource):
    @console_ns.doc("get_average_session_interaction_statistics")
    @console_ns.doc(description="Get average session interaction statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Average session interaction statistics retrieved successfully",
        fields.List(fields.Raw(description="Average session interaction data")),
    )
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT])
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("c.created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    AVG(subquery.message_count) AS interactions
FROM
    (
        SELECT
            m.conversation_id,
            COUNT(m.id) AS message_count
        FROM
            conversations c
        JOIN
            messages m
            ON c.id = m.conversation_id
        WHERE
            c.app_id = :app_id
            AND m.invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND c.created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND c.created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += """
        GROUP BY m.conversation_id
    ) subquery
LEFT JOIN
    conversations c
    ON c.id = subquery.conversation_id
GROUP BY
    date
ORDER BY
    date"""

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append(
                    {"date": str(i.date), "interactions": float(i.interactions.quantize(Decimal("0.01")))}
                )

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/user-satisfaction-rate")
class UserSatisfactionRateStatistic(Resource):
    @console_ns.doc("get_user_satisfaction_rate_statistics")
    @console_ns.doc(description="Get user satisfaction rate statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "User satisfaction rate statistics retrieved successfully",
        fields.List(fields.Raw(description="User satisfaction rate data")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("m.created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    COUNT(m.id) AS message_count,
    COUNT(mf.id) AS feedback_count
FROM
    messages m
LEFT JOIN
    message_feedbacks mf
    ON mf.message_id=m.id AND mf.rating='like'
WHERE
    m.app_id = :app_id
    AND m.invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND m.created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND m.created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date ORDER BY date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append(
                    {
                        "date": str(i.date),
                        "rate": round((i.feedback_count * 1000 / i.message_count) if i.message_count > 0 else 0, 2),
                    }
                )

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/average-response-time")
class AverageResponseTimeStatistic(Resource):
    @console_ns.doc("get_average_response_time_statistics")
    @console_ns.doc(description="Get average response time statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Average response time statistics retrieved successfully",
        fields.List(fields.Raw(description="Average response time data")),
    )
    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=AppMode.COMPLETION)
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    AVG(provider_response_latency) AS latency
FROM
    messages
WHERE
    app_id = :app_id
    AND invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date ORDER BY date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({"date": str(i.date), "latency": round(i.latency * 1000, 4)})

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/tokens-per-second")
class TokensPerSecondStatistic(Resource):
    @console_ns.doc("get_tokens_per_second_statistics")
    @console_ns.doc(description="Get tokens per second statistics for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Tokens per second statistics retrieved successfully",
        fields.List(fields.Raw(description="Tokens per second data")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()
        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    CASE
        WHEN SUM(provider_response_latency) = 0 THEN 0
        ELSE (SUM(answer_tokens) / SUM(provider_response_latency))
    END as tokens_per_second
FROM
    messages
WHERE
    app_id = :app_id
    AND invoke_from != :invoke_from"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date ORDER BY date"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append({"date": str(i.date), "tps": round(i.tokens_per_second, 4)})

        return jsonify({"data": response_data})


@console_ns.route("/apps/<uuid:app_id>/statistics/town-distribution")
class TownDistributionStatistic(Resource):
    @console_ns.doc("get_town_distribution_statistics")
    @console_ns.doc(description="Get conversation distribution by town for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Town distribution statistics retrieved successfully",
        fields.List(fields.Raw(description="Per-town conversation and user counts")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        # 小程序把户籍地作为 inputs.address 传入，格式为「乡镇·村」，取 · 前半段即乡镇/街道。
        # inputs 为 json（非 jsonb）列，故用 ->> 取文本值。
        # 未选户籍地的会话 town 归为 NULL，单独作为 unspecified 返回，与各乡镇共用同一套
        # 过滤条件，保证「各乡镇之和 + unspecified = 该时间段总会话数」。
        # 老数据 invoke_from 可能为 NULL，需显式保留（SQL 三值逻辑下 != 会连同 NULL 行一起丢弃）。
        sql_query = """SELECT
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') AS town,
    COUNT(*) AS conversation_count,
    COUNT(DISTINCT from_end_user_id) AS user_count
FROM
    conversations
WHERE
    app_id = :app_id
    AND is_deleted IS false
    AND (invoke_from IS NULL OR invoke_from != :invoke_from)"""
        arg_dict = {"app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY town ORDER BY conversation_count DESC, town"

        response_data = []
        unspecified_count = 0
        unspecified_user_count = 0

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                if i.town is None:
                    unspecified_count = i.conversation_count
                    unspecified_user_count = i.user_count
                    continue
                response_data.append(
                    {
                        "town": i.town,
                        "conversation_count": i.conversation_count,
                        "user_count": i.user_count,
                    }
                )

        return jsonify(
            {
                "data": response_data,
                "unspecified_count": unspecified_count,
                "unspecified_user_count": unspecified_user_count,
            }
        )


@console_ns.route("/apps/<uuid:app_id>/statistics/town-trend")
class TownTrendStatistic(Resource):
    @console_ns.doc("get_town_trend_statistics")
    @console_ns.doc(description="Get daily conversation counts per town for an application")
    @console_ns.doc(params={"app_id": "Application ID"})
    @console_ns.expect(console_ns.models[StatisticTimeRangeQuery.__name__])
    @console_ns.response(
        200,
        "Town trend statistics retrieved successfully",
        fields.List(fields.Raw(description="Per-day per-town conversation counts")),
    )
    @get_app_model
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, app_model):
        account, _ = current_account_with_tenant()

        args = StatisticTimeRangeQuery.model_validate(request.args.to_dict(flat=True))  # type: ignore

        # 按【日期 × 乡镇】二维分组，供前端画趋势折线。
        # 过滤条件与 town-distribution 保持一致；未填写户籍地的会话 town 为 NULL，此处直接排除，
        # 趋势图只看各乡镇自身的变化。
        converted_created_at = convert_datetime_to_date("created_at")
        sql_query = f"""SELECT
    {converted_created_at} AS date,
    NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') AS town,
    COUNT(*) AS conversation_count
FROM
    conversations
WHERE
    app_id = :app_id
    AND is_deleted IS false
    AND (invoke_from IS NULL OR invoke_from != :invoke_from)
    AND NULLIF(split_part(COALESCE(inputs ->> 'address', ''), '·', 1), '') IS NOT NULL"""
        arg_dict = {"tz": account.timezone, "app_id": app_model.id, "invoke_from": InvokeFrom.DEBUGGER}
        assert account.timezone is not None

        try:
            start_datetime_utc, end_datetime_utc = parse_time_range(args.start, args.end, account.timezone)
        except ValueError as e:
            abort(400, description=str(e))

        if start_datetime_utc:
            sql_query += " AND created_at >= :start"
            arg_dict["start"] = start_datetime_utc

        if end_datetime_utc:
            sql_query += " AND created_at < :end"
            arg_dict["end"] = end_datetime_utc

        sql_query += " GROUP BY date, town ORDER BY date, town"

        response_data = []

        with db.engine.begin() as conn:
            rs = conn.execute(sa.text(sql_query), arg_dict)
            for i in rs:
                response_data.append(
                    {
                        "date": str(i.date),
                        "town": i.town,
                        "conversation_count": i.conversation_count,
                    }
                )

        return jsonify({"data": response_data})
