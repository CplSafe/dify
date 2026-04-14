"""Unit tests for the allocation console endpoints.

Covers:

- happy path POST allocate / GET list
- error mapping from ``AllocationService`` domain exceptions
  (NotTenantMember -> 404, InsufficientTenantBalance / InsufficientMemberBalance -> 409,
  ValueError / payload errors -> 400)

Same fixture pattern as ``test_topup_orders.py`` — auth decorators are
no-op'd so the controller can be invoked directly without a real DB.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.views import MethodView

from services.wallet.exceptions import (
    InsufficientMemberBalance,
    InsufficientTenantBalance,
    NotTenantMember,
)

if not hasattr(builtins, "MethodView"):
    builtins.MethodView = MethodView  # type: ignore[attr-defined]


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def allocation_module(monkeypatch: pytest.MonkeyPatch):
    """Reload the allocation controller with auth decorators no-oped."""
    from controllers.console import console_ns, wraps
    from libs import login

    def _noop(func):
        return func

    monkeypatch.setattr(login, "login_required", _noop)
    monkeypatch.setattr(wraps, "setup_required", _noop)
    monkeypatch.setattr(wraps, "account_initialization_required", _noop)
    monkeypatch.setattr(wraps, "tenant_owner_required", _noop)

    def _noop_route(*args, **kwargs):
        def _decorator(cls):
            return cls

        return _decorator

    monkeypatch.setattr(console_ns, "route", _noop_route)

    module_name = "controllers.console.workspace.allocation"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _fake_allocation_record(
    *,
    amount: Decimal = Decimal("25.00"),
    description: str | None = "Q2 budget",
) -> MagicMock:
    record = MagicMock()
    record.id = "alloc-uuid"
    record.tenant_id = "tenant-1"
    record.account_id = "member-1"
    record.operator_id = "owner-1"
    record.amount = amount
    record.description = description
    record.created_at = datetime(2026, 4, 14, 12, 0, 0)
    return record


def _install_current_account(module, monkeypatch, account_id="owner-1", tenant_id="tenant-1"):
    account = MagicMock()
    account.id = account_id
    monkeypatch.setattr(
        module, "current_account_with_tenant", lambda: (account, tenant_id)
    )


# ---------------------------------------------------------------------------
# POST /workspaces/current/members/<member_id>/allocations
# ---------------------------------------------------------------------------


class TestCreateAllocation:
    def test_happy_path_allocate_returns_201(self, app, allocation_module, monkeypatch):
        _install_current_account(allocation_module, monkeypatch)
        record = _fake_allocation_record(amount=Decimal("25.00"))
        monkeypatch.setattr(
            allocation_module.AllocationService,
            "allocate",
            classmethod(lambda cls, **kwargs: record),
        )

        with app.test_request_context(
            "/", method="POST", json={"amount": "25.00", "description": "Q2 budget"}
        ):
            body, status = allocation_module.MemberAllocationApi().post("member-1")

        assert status == 201
        assert body == {
            "id": "alloc-uuid",
            "tenant_id": "tenant-1",
            "account_id": "member-1",
            "operator_id": "owner-1",
            "amount": "25.00",
            "description": "Q2 budget",
            "created_at": "2026-04-14T12:00:00",
        }

    def test_happy_path_reclaim_negative_amount(self, app, allocation_module, monkeypatch):
        _install_current_account(allocation_module, monkeypatch)
        captured = {}

        def _fake_allocate(cls, **kwargs):
            captured.update(kwargs)
            return _fake_allocation_record(amount=Decimal("-15.00"))

        monkeypatch.setattr(
            allocation_module.AllocationService, "allocate", classmethod(_fake_allocate)
        )

        with app.test_request_context("/", method="POST", json={"amount": "-15.00"}):
            body, status = allocation_module.MemberAllocationApi().post("member-1")

        assert status == 201
        assert captured["amount"] == Decimal("-15.00")
        assert captured["account_id"] == "member-1"
        assert captured["operator_id"] == "owner-1"

    @pytest.mark.parametrize(
        "payload",
        [
            {},  # missing amount
            {"amount": ""},  # empty string
            {"amount": "not-a-number"},
            {"amount": None},
        ],
    )
    def test_invalid_payload_raises_400(self, app, allocation_module, monkeypatch, payload):
        _install_current_account(allocation_module, monkeypatch)
        monkeypatch.setattr(
            allocation_module.AllocationService,
            "allocate",
            classmethod(lambda cls, **kwargs: _fake_allocation_record()),
        )

        with app.test_request_context("/", method="POST", json=payload):
            with pytest.raises(allocation_module.AllocationAmountInvalidError) as exc:
                allocation_module.MemberAllocationApi().post("member-1")
        assert exc.value.code == 400

    def test_zero_amount_returns_400(self, app, allocation_module, monkeypatch):
        """Service raises ValueError on zero — controller maps to 400."""
        _install_current_account(allocation_module, monkeypatch)
        monkeypatch.setattr(
            allocation_module.AllocationService,
            "allocate",
            classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(ValueError("amount must be non-zero"))),
        )

        with app.test_request_context("/", method="POST", json={"amount": "0"}):
            with pytest.raises(allocation_module.AllocationAmountInvalidError) as exc:
                allocation_module.MemberAllocationApi().post("member-1")
        assert exc.value.code == 400

    def test_not_tenant_member_returns_404(self, app, allocation_module, monkeypatch):
        _install_current_account(allocation_module, monkeypatch)
        monkeypatch.setattr(
            allocation_module.AllocationService,
            "allocate",
            classmethod(lambda cls, **kwargs: (_ for _ in ()).throw(NotTenantMember("nope"))),
        )

        with app.test_request_context("/", method="POST", json={"amount": "10"}):
            with pytest.raises(allocation_module.AllocationMemberNotFoundError) as exc:
                allocation_module.MemberAllocationApi().post("nobody")
        assert exc.value.code == 404

    def test_insufficient_tenant_balance_returns_409(
        self, app, allocation_module, monkeypatch
    ):
        _install_current_account(allocation_module, monkeypatch)
        monkeypatch.setattr(
            allocation_module.AllocationService,
            "allocate",
            classmethod(
                lambda cls, **kwargs: (_ for _ in ()).throw(InsufficientTenantBalance("low"))
            ),
        )

        with app.test_request_context("/", method="POST", json={"amount": "1000000"}):
            with pytest.raises(
                allocation_module.AllocationInsufficientTenantBalanceError
            ) as exc:
                allocation_module.MemberAllocationApi().post("member-1")
        assert exc.value.code == 409

    def test_insufficient_member_balance_returns_409(
        self, app, allocation_module, monkeypatch
    ):
        _install_current_account(allocation_module, monkeypatch)
        monkeypatch.setattr(
            allocation_module.AllocationService,
            "allocate",
            classmethod(
                lambda cls, **kwargs: (_ for _ in ()).throw(InsufficientMemberBalance("low"))
            ),
        )

        with app.test_request_context("/", method="POST", json={"amount": "-1000000"}):
            with pytest.raises(
                allocation_module.AllocationInsufficientMemberBalanceError
            ) as exc:
                allocation_module.MemberAllocationApi().post("member-1")
        assert exc.value.code == 409


# ---------------------------------------------------------------------------
# GET /workspaces/current/allocations
# ---------------------------------------------------------------------------


class TestListAllocations:
    def test_returns_paginated_records(self, app, allocation_module, monkeypatch):
        _install_current_account(allocation_module, monkeypatch)
        monkeypatch.setattr(
            allocation_module.AllocationService,
            "list_tenant_allocations",
            classmethod(lambda cls, **kwargs: ([_fake_allocation_record()], 1)),
        )

        with app.test_request_context("/?limit=10&offset=0"):
            body, status = allocation_module.TenantAllocationListApi().get()

        assert status == 200
        assert body["total"] == 1
        assert body["limit"] == 10
        assert body["offset"] == 0
        assert body["data"][0]["amount"] == "25.00"
        assert body["data"][0]["description"] == "Q2 budget"

    def test_limit_capped_at_100(self, app, allocation_module, monkeypatch):
        _install_current_account(allocation_module, monkeypatch)
        captured = {}

        def _fake_list(cls, **kwargs):
            captured.update(kwargs)
            return ([], 0)

        monkeypatch.setattr(
            allocation_module.AllocationService,
            "list_tenant_allocations",
            classmethod(_fake_list),
        )

        with app.test_request_context("/?limit=9999"):
            allocation_module.TenantAllocationListApi().get()

        assert captured["limit"] == 100
