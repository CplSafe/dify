from types import SimpleNamespace

import pytest
from werkzeug.exceptions import Forbidden, NotFound

from controllers.web import town_statistic


class _Connection:
    def __init__(self, result_sets):
        self.result_sets = iter(result_sets)

    def execute(self, _query, _args):
        return next(self.result_sets)


class _ConnectionContext:
    def __init__(self, result_sets):
        self.connection = _Connection(result_sets)

    def __enter__(self):
        return self.connection

    def __exit__(self, _exc_type, _exc, _tb):
        return False


def _install_db(monkeypatch: pytest.MonkeyPatch, *, site=None, app_model=None, result_sets=((), ())):
    session = SimpleNamespace(
        scalar=lambda _query: site,
        get=lambda _model, _id: app_model,
    )
    engine = SimpleNamespace(begin=lambda: _ConnectionContext(result_sets))
    monkeypatch.setattr(town_statistic, "db", SimpleNamespace(session=session, engine=engine))


def test_distribution_allows_anonymous_access_with_share_code(app, monkeypatch: pytest.MonkeyPatch):
    site = SimpleNamespace(app_id="app-1")
    app_model = SimpleNamespace(id="app-1", enable_site=True)
    town_rows = [SimpleNamespace(town="赫山街道", conversation_count=3, user_count=2)]
    village_rows = [SimpleNamespace(town="赫山街道", village="洪家村社区", conversation_count=2, user_count=1)]
    _install_db(monkeypatch, site=site, app_model=app_model, result_sets=(town_rows, village_rows))
    monkeypatch.setattr(town_statistic, "parse_time_range", lambda *_args: (None, None))

    with app.test_request_context(
        "/api/town-statistics/distribution",
        headers={"X-App-Code": "public-code"},
    ):
        response = town_statistic.PublicTownDistributionStatistic().get()

    assert response.get_json() == {
        "data": [{"town": "赫山街道", "conversation_count": 3, "user_count": 2}],
        "villages": [
            {
                "town": "赫山街道",
                "village": "洪家村社区",
                "conversation_count": 2,
                "user_count": 1,
            }
        ],
        "unspecified_count": 0,
        "unspecified_user_count": 0,
    }


def test_distribution_rejects_unknown_share_code(app, monkeypatch: pytest.MonkeyPatch):
    _install_db(monkeypatch, site=None)

    with app.test_request_context(
        "/api/town-statistics/distribution",
        headers={"X-App-Code": "unknown"},
    ):
        with pytest.raises(NotFound):
            town_statistic.PublicTownDistributionStatistic().get()


def test_distribution_rejects_disabled_site(app, monkeypatch: pytest.MonkeyPatch):
    site = SimpleNamespace(app_id="app-1")
    app_model = SimpleNamespace(id="app-1", enable_site=False)
    _install_db(monkeypatch, site=site, app_model=app_model)

    with app.test_request_context(
        "/api/town-statistics/distribution",
        headers={"X-App-Code": "public-code"},
    ):
        with pytest.raises(Forbidden):
            town_statistic.PublicTownDistributionStatistic().get()
