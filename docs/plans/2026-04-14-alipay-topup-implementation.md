# 支付宝充值 + 工作空间钱包体系 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Dify 实现支付宝扫码充值 + 工作空间两级钱包（Tenant + User）+ 预算分配体系，替换现有"超管手动充值"为用户自助充值。

**Architecture:** Tenant 钱包通过支付宝当面付充值，owner/admin 把额度分配给成员（严格预算锁定，可回收），workflow 消费时同时扣 Tenant.locked 和 User.balance。任一为 0 即停服。Provider 抽象层预留微信支付接入点。

**Tech Stack:**
- 后端：Flask + SQLAlchemy + Alembic + Celery + pydantic-settings + `alipay-sdk-python`
- 前端：Next.js + TanStack Query + `qrcode.react`
- 测试：pytest（单元 + containers 集成）+ Vitest

**Design doc**: `docs/plans/2026-04-14-alipay-topup-design.md`

---

## Phase 0：准备工作

### Task 0.1：创建工作分支

**Step 1：检查当前分支状态**

Run: `git status && git branch --show-current`
Expected: 显示 `dify-zd` 分支，工作区可能有未提交修改

**Step 2：基于 dify-zd 创建 feature 分支**

Run: `git checkout -b feat/alipay-topup-wallet`
Expected: Switched to a new branch 'feat/alipay-topup-wallet'

---

### Task 0.2：添加 Python 依赖

**Files:**
- Modify: `api/pyproject.toml`

**Step 1：添加 alipay-sdk-python**

Run: `cd api && uv add alipay-sdk-python`
Expected: `alipay-sdk-python` 出现在 `pyproject.toml` 的 dependencies 中，`uv.lock` 更新

**Step 2：验证安装**

Run: `cd api && uv run python -c "from alipay.aop.api.AlipayClientConfig import AlipayClientConfig; print('OK')"`
Expected: 输出 `OK`

**Step 3：提交**

```bash
git add api/pyproject.toml api/uv.lock
git commit -m "chore: add alipay-sdk-python dependency"
```

---

### Task 0.3：添加前端依赖

**Files:**
- Modify: `web/package.json`

**Step 1：添加 qrcode.react**

Run: `cd web && pnpm add qrcode.react`
Expected: `qrcode.react` 出现在 dependencies 中

**Step 2：提交**

```bash
git add web/package.json web/pnpm-lock.yaml
git commit -m "chore: add qrcode.react for payment QR rendering"
```

---

### Task 0.4：配置 .gitignore 和 secrets 目录

**Files:**
- Modify: `.gitignore`
- Create: `api/secrets/README.md`
- Create: `api/secrets/.gitkeep`

**Step 1：编辑 .gitignore，新增**

```
# Payment provider secrets (PEM keys etc.)
api/secrets/
!api/secrets/README.md
!api/secrets/.gitkeep
*.pem
```

**Step 2：创建 README**

`api/secrets/README.md` 内容：
```markdown
# Payment Provider Secrets

This directory holds PEM keys and other sensitive credentials for payment providers.

**Never commit any actual secrets.** Only `README.md` and `.gitkeep` are tracked.

## Alipay

Place these files locally (or mount via K8s Secret in production):
- `alipay/app_private_key.pem` — Merchant application private key
- `alipay/alipay_public_key.pem` — Alipay platform public key

Configure paths in `api/.env`:
```
ALIPAY_APP_PRIVATE_KEY_PATH=/path/to/api/secrets/alipay/app_private_key.pem
ALIPAY_PUBLIC_KEY_PATH=/path/to/api/secrets/alipay/alipay_public_key.pem
```
```

**Step 3：创建 .gitkeep 占位**

```bash
touch api/secrets/.gitkeep
```

**Step 4：提交**

```bash
git add .gitignore api/secrets/README.md api/secrets/.gitkeep
git commit -m "chore: add api/secrets/ for payment provider PEM keys"
```

---

## Phase 1：数据模型 + 迁移

### Task 1.1：定义 TenantBalance / PaymentOrder / AllocationRecord 模型

**Files:**
- Modify: `api/models/creator.py`
- Test: `api/tests/unit_tests/models/test_payment_models.py`

**Step 1：写失败的测试**

`api/tests/unit_tests/models/test_payment_models.py`:
```python
"""Unit tests for payment-related models."""
from decimal import Decimal

from models.creator import (
    AllocationRecord,
    BillingRecordType,
    PaymentOrder,
    TenantBalance,
)


class TestTenantBalance:
    def test_default_values(self):
        b = TenantBalance(tenant_id="t1")
        assert b.balance == Decimal(0)
        assert b.locked == Decimal(0)
        assert b.total_topup == Decimal(0)
        assert b.currency == "CNY"

    def test_total_property(self):
        b = TenantBalance(tenant_id="t1")
        b.balance = Decimal("100")
        b.locked = Decimal("50")
        assert b.total == Decimal("150")


class TestPaymentOrder:
    def test_required_fields(self):
        o = PaymentOrder(
            provider="alipay",
            out_trade_no="abc",
            tenant_id="t1",
            account_id="a1",
            amount=Decimal("10"),
            amount_fen=1000,
            subject="test",
            status="pending",
            expires_at=None,  # set in real test below
        )
        assert o.provider == "alipay"
        assert o.amount_fen == 1000


class TestAllocationRecord:
    def test_signed_amount(self):
        positive = AllocationRecord(
            tenant_id="t1",
            account_id="a1",
            operator_id="op1",
            amount=Decimal("50"),
        )
        negative = AllocationRecord(
            tenant_id="t1",
            account_id="a1",
            operator_id="op1",
            amount=Decimal("-30"),
        )
        assert positive.amount > 0
        assert negative.amount < 0


class TestBillingRecordType:
    def test_allocation_enum(self):
        assert BillingRecordType.ALLOCATION.value == "allocation"
```

**Step 2：跑测试确认失败**

Run: `cd api && uv run pytest tests/unit_tests/models/test_payment_models.py -v`
Expected: ImportError 或 AttributeError（模型未定义）

**Step 3：在 `api/models/creator.py` 添加新模型**

在文件末尾追加：
```python
class PaymentProviderName(enum.StrEnum):
    ALIPAY = "alipay"
    WECHAT = "wechat"


class PaymentOrderStatus(enum.StrEnum):
    PENDING = "pending"
    PAID = "paid"
    CLOSED = "closed"
    REFUNDED = "refunded"
    FAILED = "failed"


class TenantBalance(TypeBase):
    """Workspace-level wallet."""

    __tablename__ = "tenant_balances"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="tenant_balance_pkey"),
        sa.Index("tenant_balance_tenant_id_idx", "tenant_id", unique=True),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0)
    )
    locked: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0)
    )
    total_topup: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0)
    )
    currency: Mapped[str] = mapped_column(String(10), server_default="CNY", default="CNY")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )

    @property
    def total(self) -> Decimal:
        return self.balance + self.locked


class PaymentOrder(TypeBase):
    """Top-up payment order, provider-agnostic."""

    __tablename__ = "payment_orders"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="payment_order_pkey"),
        sa.Index("payment_order_out_trade_no_idx", "out_trade_no", unique=True),
        sa.Index("payment_order_tenant_status_idx", "tenant_id", "status"),
        sa.Index("payment_order_provider_trade_idx", "provider", "provider_trade_no"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_trade_no: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(precision=20, scale=6), nullable=False)
    amount_fen: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentOrderStatus.PENDING.value)
    qr_code: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    prepay_raw: Mapped[str | None] = mapped_column(LongText, nullable=True, default=None)
    notify_raw: Mapped[str | None] = mapped_column(LongText, nullable=True, default=None)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "out_trade_no": self.out_trade_no,
            "provider_trade_no": self.provider_trade_no,
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "amount": str(self.amount),
            "amount_fen": self.amount_fen,
            "subject": self.subject,
            "status": self.status,
            "qr_code": self.qr_code,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
        }


class AllocationRecord(TypeBase):
    """Ledger for tenant -> member fund movements."""

    __tablename__ = "allocation_records"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="allocation_record_pkey"),
        sa.Index("alloc_tenant_created_idx", "tenant_id", "created_at"),
        sa.Index("alloc_member_idx", "account_id"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    operator_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(precision=20, scale=6), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "operator_id": self.operator_id,
            "amount": str(self.amount),
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }
```

同时把 `BillingRecordType` 加上 `ALLOCATION = "allocation"`。

**Step 4：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/models/test_payment_models.py -v`
Expected: 全部 PASS

**Step 5：提交**

```bash
git add api/models/creator.py api/tests/unit_tests/models/test_payment_models.py
git commit -m "feat: add TenantBalance, PaymentOrder, AllocationRecord models"
```

---

### Task 1.2：BillingRecord 添加 scope 字段

**Files:**
- Modify: `api/models/creator.py` (BillingRecord 类)

**Step 1：添加 scope 列 + Enum**

在 `BillingRecord` 类内、`description` 字段附近加：
```python
scope: Mapped[str] = mapped_column(String(20), server_default="user", default="user")
```

`to_dict()` 方法返回值里加上 `"scope": self.scope`。

**Step 2：扩展测试**

在 `test_payment_models.py` 加：
```python
def test_billing_record_scope_default():
    from models.creator import BillingRecord
    r = BillingRecord(account_id="a1", amount=Decimal("1"), record_type="topup")
    assert r.scope == "user"
```

**Step 3：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/models/test_payment_models.py -v`
Expected: PASS

**Step 4：提交**

```bash
git add api/models/creator.py api/tests/unit_tests/models/test_payment_models.py
git commit -m "feat: add scope column to BillingRecord (tenant|user)"
```

---

### Task 1.3：在 models/__init__.py 导出新模型

**Files:**
- Modify: `api/models/__init__.py`

**Step 1：找到 creator 模型 import 段**

Run: `grep -n "creator" api/models/__init__.py`

**Step 2：把新的三个模型加进 import 和 `__all__`**

```python
from .creator import (
    AllocationRecord,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentProviderName,
    TenantBalance,
    # ... existing
)
```
更新 `__all__` 列表。

**Step 3：验证**

Run: `cd api && uv run python -c "from models import TenantBalance, PaymentOrder, AllocationRecord; print('OK')"`
Expected: `OK`

**Step 4：提交**

```bash
git add api/models/__init__.py
git commit -m "chore: export new payment models from models package"
```

---

### Task 1.4：编写 Alembic 迁移脚本

**Files:**
- Create: `api/migrations/versions/<timestamp>_add_payment_and_tenant_balance.py`

**Step 1：自动生成迁移**

Run: `cd api && uv run flask db migrate -m "add payment and tenant balance"`
Expected: 生成新文件 `api/migrations/versions/<hash>_add_payment_and_tenant_balance.py`

**Step 2：人工 review + 修正**

打开生成的迁移文件，确认：
- `op.create_table('tenant_balances', ...)` 包含所有字段
- `op.create_table('payment_orders', ...)` 包含所有字段
- `op.create_table('allocation_records', ...)` 包含所有字段
- `op.add_column('billing_records', sa.Column('scope', sa.String(20), server_default='user', nullable=False))`
- 全部索引齐全

**Step 3：在 upgrade() 末尾加数据回填逻辑**

```python
# 数据迁移：把现有 UserBalance 提升为 TenantBalance.locked
def upgrade():
    # ... 自动生成的 schema 变更 ...

    # 数据回填
    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT ub.account_id, ub.balance
        FROM user_balances ub
        WHERE ub.balance > 0
    """)).fetchall()

    for row in rows:
        # 找该 account 的最早 owner tenant
        tenant_row = conn.execute(sa.text("""
            SELECT tenant_id FROM tenant_account_joins
            WHERE account_id = :aid AND role = 'owner'
            ORDER BY created_at ASC LIMIT 1
        """), {"aid": row.account_id}).fetchone()

        if not tenant_row:
            continue

        tenant_id = tenant_row.tenant_id
        amount = row.balance

        # 插入 tenant_balances
        conn.execute(sa.text("""
            INSERT INTO tenant_balances (id, tenant_id, balance, locked, total_topup, currency)
            VALUES (gen_random_uuid(), :tid, 0, :amt, :amt, 'CNY')
            ON CONFLICT (tenant_id) DO UPDATE
            SET locked = tenant_balances.locked + EXCLUDED.locked,
                total_topup = tenant_balances.total_topup + EXCLUDED.total_topup
        """), {"tid": tenant_id, "amt": amount})

        # 写一条 allocation_records
        conn.execute(sa.text("""
            INSERT INTO allocation_records (id, tenant_id, account_id, operator_id, amount, description)
            VALUES (gen_random_uuid(), :tid, :aid, :aid, :amt, '数据迁移：历史余额转入')
        """), {"tid": tenant_id, "aid": row.account_id, "amt": amount})
```

**Step 4：执行迁移**

Run: `cd api && uv run flask db upgrade`
Expected: 输出 `Running upgrade ...`，无报错

**Step 5：验证表结构**

Run: `cd api && uv run python -c "from models import TenantBalance; from extensions.ext_database import db; from app_factory import create_app; app = create_app(); ctx = app.app_context(); ctx.push(); print(db.session.query(TenantBalance).count())"`
Expected: 输出某个数字（0 或老用户数）

**Step 6：提交**

```bash
git add api/migrations/versions/*.py
git commit -m "feat: migrate schema for payment + tenant balance + backfill"
```

---

## Phase 2：钱包服务 + 扣费改造

### Task 2.1：TenantBalanceService（基础读写）

**Files:**
- Create: `api/services/wallet/__init__.py`
- Create: `api/services/wallet/tenant_balance_service.py`
- Test: `api/tests/unit_tests/services/wallet/test_tenant_balance_service.py`

**Step 1：写失败的测试**

`api/tests/unit_tests/services/wallet/test_tenant_balance_service.py`：
```python
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.wallet.tenant_balance_service import TenantBalanceService


@patch("services.wallet.tenant_balance_service.db")
def test_get_or_create_creates_when_missing(mock_db):
    mock_db.session.scalar.return_value = None
    result = TenantBalanceService.get_or_create("t-1")
    assert result.tenant_id == "t-1"
    assert result.balance == Decimal(0)
    mock_db.session.add.assert_called()
    mock_db.session.commit.assert_called()


@patch("services.wallet.tenant_balance_service.db")
def test_get_or_create_returns_existing(mock_db):
    from models.creator import TenantBalance
    existing = TenantBalance(tenant_id="t-1")
    existing.balance = Decimal("100")
    mock_db.session.scalar.return_value = existing
    result = TenantBalanceService.get_or_create("t-1")
    assert result.balance == Decimal("100")
    mock_db.session.add.assert_not_called()
```

**Step 2：跑测试确认失败**

Run: `cd api && uv run pytest tests/unit_tests/services/wallet/test_tenant_balance_service.py -v`
Expected: ImportError

**Step 3：实现 service**

`api/services/wallet/__init__.py`：空文件

`api/services/wallet/tenant_balance_service.py`：
```python
"""Tenant-level wallet operations."""
import logging
from decimal import Decimal

from sqlalchemy import select

from extensions.ext_database import db
from models.creator import TenantBalance

logger = logging.getLogger(__name__)


class TenantBalanceService:
    """Read/write operations on TenantBalance."""

    @classmethod
    def get_or_create(cls, tenant_id: str) -> TenantBalance:
        balance = db.session.scalar(
            select(TenantBalance).where(TenantBalance.tenant_id == tenant_id)
        )
        if balance is None:
            balance = TenantBalance(tenant_id=tenant_id)
            db.session.add(balance)
            db.session.commit()
        return balance

    @classmethod
    def get(cls, tenant_id: str) -> TenantBalance | None:
        return db.session.scalar(
            select(TenantBalance).where(TenantBalance.tenant_id == tenant_id)
        )

    @classmethod
    def has_funds(cls, tenant_id: str) -> bool:
        b = cls.get(tenant_id)
        return b is not None and (b.balance > 0 or b.locked > 0)
```

**Step 4：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/services/wallet/test_tenant_balance_service.py -v`
Expected: PASS

**Step 5：提交**

```bash
git add api/services/wallet/ api/tests/unit_tests/services/wallet/
git commit -m "feat: add TenantBalanceService for tenant wallet read/write"
```

---

### Task 2.2：AllocationService（分配/回收 + 不变式校验）

**Files:**
- Create: `api/services/wallet/allocation_service.py`
- Create: `api/services/wallet/exceptions.py`
- Test: `api/tests/unit_tests/services/wallet/test_allocation_service.py`

**Step 1：写异常类**

`api/services/wallet/exceptions.py`：
```python
class WalletError(Exception):
    """Base exception for wallet operations."""


class InsufficientTenantBalance(WalletError):
    code = "ALLOCATION_EXCEEDS_BALANCE"


class InsufficientMemberBalance(WalletError):
    code = "RECLAIM_EXCEEDS_MEMBER_BALANCE"


class NotTenantMember(WalletError):
    code = "NOT_TENANT_MEMBER"
```

**Step 2：写失败的测试**

`api/tests/unit_tests/services/wallet/test_allocation_service.py`：
```python
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.wallet.allocation_service import AllocationService
from services.wallet.exceptions import (
    InsufficientMemberBalance,
    InsufficientTenantBalance,
)


@patch("services.wallet.allocation_service._verify_tenant_member")
@patch("services.wallet.allocation_service.UserBillingService")
@patch("services.wallet.allocation_service.TenantBalanceService")
@patch("services.wallet.allocation_service.db")
def test_allocate_decreases_tenant_balance_and_increases_user(mock_db, mock_tb_svc, mock_ub_svc, mock_verify):
    from models.creator import TenantBalance, UserBalance
    tenant_balance = TenantBalance(tenant_id="t1")
    tenant_balance.balance = Decimal("100")
    tenant_balance.locked = Decimal("0")
    user_balance = UserBalance(account_id="a1")
    user_balance.balance = Decimal("0")

    mock_tb_svc.get_or_create.return_value = tenant_balance
    mock_ub_svc.get_or_create_balance.return_value = user_balance

    AllocationService.allocate(
        tenant_id="t1", account_id="a1", operator_id="op", amount=Decimal("30")
    )

    assert tenant_balance.balance == Decimal("70")
    assert tenant_balance.locked == Decimal("30")
    assert user_balance.balance == Decimal("30")


def test_allocate_rejects_when_insufficient():
    with pytest.raises(InsufficientTenantBalance):
        # over-allocation: balance=10, allocate 50
        with patch("services.wallet.allocation_service._verify_tenant_member"), \
             patch("services.wallet.allocation_service.UserBillingService"), \
             patch("services.wallet.allocation_service.TenantBalanceService") as mtb, \
             patch("services.wallet.allocation_service.db"):
            from models.creator import TenantBalance
            tb = TenantBalance(tenant_id="t1")
            tb.balance = Decimal("10")
            tb.locked = Decimal("0")
            mtb.get_or_create.return_value = tb
            AllocationService.allocate(
                tenant_id="t1", account_id="a1", operator_id="op", amount=Decimal("50")
            )


def test_reclaim_rejects_when_member_insufficient():
    with pytest.raises(InsufficientMemberBalance):
        with patch("services.wallet.allocation_service._verify_tenant_member"), \
             patch("services.wallet.allocation_service.UserBillingService") as mub, \
             patch("services.wallet.allocation_service.TenantBalanceService") as mtb, \
             patch("services.wallet.allocation_service.db"):
            from models.creator import TenantBalance, UserBalance
            tb = TenantBalance(tenant_id="t1")
            tb.balance = Decimal("0"); tb.locked = Decimal("10")
            ub = UserBalance(account_id="a1"); ub.balance = Decimal("10")
            mtb.get_or_create.return_value = tb
            mub.get_or_create_balance.return_value = ub
            AllocationService.allocate(
                tenant_id="t1", account_id="a1", operator_id="op", amount=Decimal("-50")
            )
```

**Step 3：跑测试确认失败**

Run: `cd api && uv run pytest tests/unit_tests/services/wallet/test_allocation_service.py -v`
Expected: ImportError

**Step 4：实现 AllocationService**

`api/services/wallet/allocation_service.py`：
```python
"""Allocation/reclaim operations for tenant->member fund movements."""
import logging
from decimal import Decimal

from sqlalchemy import select

from extensions.ext_database import db
from models import TenantAccountJoin
from models.creator import (
    AllocationRecord,
    BillingRecord,
    BillingRecordType,
)
from services.user_billing_service import UserBillingService
from services.wallet.exceptions import (
    InsufficientMemberBalance,
    InsufficientTenantBalance,
    NotTenantMember,
)
from services.wallet.tenant_balance_service import TenantBalanceService

logger = logging.getLogger(__name__)


def _verify_tenant_member(tenant_id: str, account_id: str) -> None:
    join = db.session.scalar(
        select(TenantAccountJoin).where(
            TenantAccountJoin.tenant_id == tenant_id,
            TenantAccountJoin.account_id == account_id,
        )
    )
    if not join:
        raise NotTenantMember(f"account {account_id} is not in tenant {tenant_id}")


class AllocationService:
    @classmethod
    def allocate(
        cls,
        *,
        tenant_id: str,
        account_id: str,
        operator_id: str,
        amount: Decimal,
        description: str | None = None,
    ) -> AllocationRecord:
        """Allocate (positive amount) or reclaim (negative amount) funds.

        Invariants enforced:
        - allocate: tenant.balance >= amount
        - reclaim: user.balance >= |amount|
        """
        if amount == 0:
            raise ValueError("amount must be non-zero")

        _verify_tenant_member(tenant_id, account_id)

        tenant_balance = TenantBalanceService.get_or_create(tenant_id)
        user_balance = UserBillingService.get_or_create_balance(account_id)

        if amount > 0:
            if tenant_balance.balance < amount:
                raise InsufficientTenantBalance(
                    f"tenant {tenant_id} has only {tenant_balance.balance}, cannot allocate {amount}"
                )
            tenant_balance.balance -= amount
            tenant_balance.locked += amount
            user_balance.balance += amount
        else:
            reclaim_amt = -amount
            if user_balance.balance < reclaim_amt:
                raise InsufficientMemberBalance(
                    f"member {account_id} has only {user_balance.balance}, cannot reclaim {reclaim_amt}"
                )
            tenant_balance.balance += reclaim_amt
            tenant_balance.locked -= reclaim_amt
            user_balance.balance -= reclaim_amt

        record = AllocationRecord(
            tenant_id=tenant_id,
            account_id=account_id,
            operator_id=operator_id,
            amount=amount,
            description=description,
        )
        billing = BillingRecord(
            account_id=account_id,
            tenant_id=tenant_id,
            amount=amount,
            record_type=BillingRecordType.ALLOCATION.value,
            scope="user",
            description=description or f"Allocation by {operator_id}",
        )
        db.session.add_all([record, billing])
        db.session.commit()

        logger.info(
            "Allocated tenant=%s account=%s amount=%s by=%s",
            tenant_id, account_id, amount, operator_id,
        )
        return record
```

**Step 5：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/services/wallet/test_allocation_service.py -v`
Expected: PASS

**Step 6：提交**

```bash
git add api/services/wallet/allocation_service.py api/services/wallet/exceptions.py api/tests/unit_tests/services/wallet/test_allocation_service.py
git commit -m "feat: add AllocationService with strict budget invariants"
```

---

### Task 2.3：改造 deduct_for_workflow_run 双扣（Tenant + User）

**Files:**
- Modify: `api/services/user_billing_service.py`
- Test: `api/tests/unit_tests/services/test_user_billing_service_dual_deduct.py`

**Step 1：写失败的测试**

```python
"""Test dual deduction (Tenant + User) for workflow runs."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.user_billing_service import UserBillingService


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_decrements_both_wallets(mock_db, mock_tb_svc):
    from models.creator import TenantBalance, UserBalance
    tb = TenantBalance(tenant_id="t1"); tb.locked = Decimal("100"); tb.balance = Decimal("0")
    ub = UserBalance(account_id="a1"); ub.balance = Decimal("100")
    mock_tb_svc.get_or_create.return_value = tb

    with patch.object(UserBillingService, "get_or_create_balance", return_value=ub):
        record = UserBillingService.deduct_for_workflow_run(
            account_id="a1", tenant_id="t1", workflow_run_id="w1",
            total_tokens=1000, price_per_1k_tokens=Decimal("0.5"),
        )

    assert ub.balance == Decimal("99.5")
    assert tb.locked == Decimal("99.5")
    # 写 2 条 BillingRecord：tenant + user
    add_calls = mock_db.session.add.call_args_list
    record_types_scopes = []
    for call in add_calls:
        obj = call.args[0]
        if hasattr(obj, "scope"):
            record_types_scopes.append((obj.record_type, obj.scope))
    assert ("deduction", "tenant") in record_types_scopes
    assert ("deduction", "user") in record_types_scopes
```

**Step 2：跑测试确认失败**

Run: `cd api && uv run pytest tests/unit_tests/services/test_user_billing_service_dual_deduct.py -v`
Expected: AssertionError

**Step 3：修改 `deduct_for_workflow_run`**

打开 `api/services/user_billing_service.py`，替换 `deduct_for_workflow_run`：

```python
@classmethod
def deduct_for_workflow_run(
    cls,
    *,
    account_id: str,
    tenant_id: str,
    workflow_run_id: str,
    total_tokens: int,
    price_per_1k_tokens: Decimal,
) -> BillingRecord | None:
    """Dual-deduct: TenantBalance.locked -= amount, UserBalance.balance -= amount.

    Both wallets are decremented atomically. UserBalance must remain >= 0.
    """
    if total_tokens <= 0:
        return None

    amount = (Decimal(total_tokens) / Decimal(1000)) * price_per_1k_tokens
    amount = amount.quantize(Decimal("0.000001"))
    if amount <= Decimal(0):
        return None

    from services.wallet.tenant_balance_service import TenantBalanceService

    user_balance = cls.get_or_create_balance(account_id)
    tenant_balance = TenantBalanceService.get_or_create(tenant_id)

    user_balance.balance -= amount
    tenant_balance.locked -= amount
    db.session.add(user_balance)
    db.session.add(tenant_balance)

    user_record = BillingRecord(
        account_id=account_id, tenant_id=tenant_id, workflow_run_id=workflow_run_id,
        amount=amount, record_type=BillingRecordType.DEDUCTION.value,
        scope="user", description=f"Workflow run {workflow_run_id}: {total_tokens} tokens",
    )
    tenant_record = BillingRecord(
        account_id=account_id, tenant_id=tenant_id, workflow_run_id=workflow_run_id,
        amount=amount, record_type=BillingRecordType.DEDUCTION.value,
        scope="tenant", description=f"Workflow run {workflow_run_id}: {total_tokens} tokens",
    )
    db.session.add_all([user_record, tenant_record])
    db.session.commit()

    logger.info(
        "Billed account=%s tenant=%s workflow=%s tokens=%d amount=%s",
        account_id, tenant_id, workflow_run_id, total_tokens, str(amount),
    )
    return user_record
```

**Step 4：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/services/test_user_billing_service_dual_deduct.py -v`
Expected: PASS

**Step 5：跑现有相关测试确保未破坏**

Run: `cd api && uv run pytest tests/test_containers_integration_tests/services/ -v -k billing`
Expected: 都 PASS（如有失败需修复 mocking）

**Step 6：提交**

```bash
git add api/services/user_billing_service.py api/tests/unit_tests/services/test_user_billing_service_dual_deduct.py
git commit -m "feat: dual-deduct from TenantBalance.locked and UserBalance"
```

---

### Task 2.4：改造可用性检查（INSUFFICIENT_USER_BUDGET 错误码）

**Files:**
- Modify: `api/services/user_billing_service.py` (`check_balance_positive`)
- Modify: `api/controllers/console/explore/completion.py:56` 调用点

**Step 1：在 `user_billing_service.py` 加新方法**

```python
@classmethod
def check_can_run(cls, account_id: str, tenant_id: str) -> tuple[bool, str | None]:
    """Returns (can_run, error_code). error_code is None if can_run."""
    user = cls.get_or_create_balance(account_id)
    if not user.is_sufficient():
        return False, "INSUFFICIENT_USER_BUDGET"
    return True, None
```

`check_balance_positive` 保留（向后兼容），调用 `check_can_run` 内部。

**Step 2：写测试**

加到 `test_user_billing_service_dual_deduct.py`：
```python
def test_check_can_run_blocks_when_user_zero():
    from models.creator import UserBalance
    ub = UserBalance(account_id="a1"); ub.balance = Decimal("0")
    with patch.object(UserBillingService, "get_or_create_balance", return_value=ub):
        ok, code = UserBillingService.check_can_run("a1", "t1")
    assert ok is False
    assert code == "INSUFFICIENT_USER_BUDGET"
```

**Step 3：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/services/test_user_billing_service_dual_deduct.py::test_check_can_run_blocks_when_user_zero -v`
Expected: PASS

**Step 4：提交**

```bash
git add api/services/user_billing_service.py api/tests/unit_tests/services/test_user_billing_service_dual_deduct.py
git commit -m "feat: add check_can_run with INSUFFICIENT_USER_BUDGET error code"
```

---

## Phase 3：支付宝集成

### Task 3.1：AlipayConfig 配置类

**Files:**
- Modify: `api/configs/feature/__init__.py`
- Modify: `api/.env.example`

**Step 1：在 feature/__init__.py 添加 AlipayConfig**

找到 `class FeatureConfig(...)` 之前，新增：

```python
class AlipayConfig(BaseSettings):
    """Alipay payment configuration."""

    ALIPAY_ENABLED: bool = Field(default=False)
    ALIPAY_APP_ID: str = Field(default="")
    ALIPAY_APP_PRIVATE_KEY_PATH: str = Field(default="")
    ALIPAY_PUBLIC_KEY_PATH: str = Field(default="")
    ALIPAY_GATEWAY: str = Field(default="https://openapi.alipay.com/gateway.do")
    ALIPAY_USE_SANDBOX: bool = Field(default=False)
    ALIPAY_NOTIFY_URL: str = Field(default="")
    ALIPAY_SIGN_TYPE: str = Field(default="RSA2")
    ALIPAY_MIN_AMOUNT_FEN: int = Field(default=100)
    ALIPAY_ORDER_TIMEOUT_MIN: int = Field(default=15)
    ALIPAY_LARGE_AMOUNT_THRESHOLD: int = Field(default=5000)
```

把 `AlipayConfig` 加到 `FeatureConfig` 的继承列表里。

**Step 2：在 api/.env.example 追加示例**

```bash
# ===========================================
# Alipay Payment (optional)
# ===========================================
ALIPAY_ENABLED=false
ALIPAY_APP_ID=
ALIPAY_APP_PRIVATE_KEY_PATH=/app/api/secrets/alipay/app_private_key.pem
ALIPAY_PUBLIC_KEY_PATH=/app/api/secrets/alipay/alipay_public_key.pem
ALIPAY_USE_SANDBOX=false
ALIPAY_NOTIFY_URL=https://your-domain.com/console/api/billing/alipay/notify
ALIPAY_MIN_AMOUNT_FEN=100
ALIPAY_ORDER_TIMEOUT_MIN=15
ALIPAY_LARGE_AMOUNT_THRESHOLD=5000
```

**Step 3：验证配置加载**

Run: `cd api && uv run python -c "from configs import dify_config; print(dify_config.ALIPAY_ENABLED)"`
Expected: `False`

**Step 4：提交**

```bash
git add api/configs/feature/__init__.py api/.env.example
git commit -m "feat: add AlipayConfig to feature settings"
```

---

### Task 3.2：PaymentProvider 抽象 + DTO

**Files:**
- Create: `api/services/payment/__init__.py`
- Create: `api/services/payment/base.py`
- Create: `api/services/payment/exceptions.py`

**Step 1：创建抽象**

`api/services/payment/__init__.py`：空
`api/services/payment/exceptions.py`：
```python
class PaymentError(Exception):
    """Base payment exception."""


class ProviderError(PaymentError):
    """Provider returned error."""


class SignatureInvalid(PaymentError):
    """Notify signature verification failed."""


class OrderNotFound(PaymentError):
    pass


class OrderExpired(PaymentError):
    pass
```

`api/services/payment/base.py`：
```python
"""Provider-agnostic payment abstraction."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class CreateOrderResult:
    qr_code: str
    raw_response: str  # JSON string for audit


@dataclass(frozen=True)
class ProviderOrderStatus:
    paid: bool
    provider_trade_no: str | None
    paid_amount: Decimal | None


@dataclass(frozen=True)
class NotifyPayload:
    out_trade_no: str
    provider_trade_no: str
    paid_amount: Decimal
    trade_status: str
    raw: dict


class PaymentProvider(Protocol):
    name: str

    def create_qr_order(
        self, *, out_trade_no: str, amount_fen: int, subject: str, notify_url: str
    ) -> CreateOrderResult: ...

    def query_order(self, *, out_trade_no: str) -> ProviderOrderStatus: ...

    def verify_notify(self, *, params: dict) -> bool: ...

    def parse_notify(self, *, params: dict) -> NotifyPayload: ...
```

**Step 2：提交（无测试，纯接口）**

```bash
git add api/services/payment/
git commit -m "feat: add PaymentProvider abstraction and DTOs"
```

---

### Task 3.3：AlipayProvider 实现

**Files:**
- Create: `api/services/payment/alipay/__init__.py`
- Create: `api/services/payment/alipay/client.py`
- Create: `api/services/payment/alipay/provider.py`
- Test: `api/tests/unit_tests/services/payment/test_alipay_provider.py`

**Step 1：写失败的测试**

```python
"""Tests for AlipayProvider."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.payment.alipay.provider import AlipayProvider


def test_provider_name():
    p = AlipayProvider.__new__(AlipayProvider)
    assert p.name == "alipay"


def test_parse_notify_extracts_fields():
    p = AlipayProvider.__new__(AlipayProvider)
    params = {
        "out_trade_no": "order123",
        "trade_no": "alipay999",
        "total_amount": "10.50",
        "trade_status": "TRADE_SUCCESS",
        "app_id": "myapp",
    }
    payload = p.parse_notify(params=params)
    assert payload.out_trade_no == "order123"
    assert payload.provider_trade_no == "alipay999"
    assert payload.paid_amount == Decimal("10.50")
    assert payload.trade_status == "TRADE_SUCCESS"
```

**Step 2：跑确认失败**

Run: `cd api && uv run pytest tests/unit_tests/services/payment/test_alipay_provider.py -v`
Expected: ImportError

**Step 3：实现 client + provider**

`api/services/payment/alipay/__init__.py`：空

`api/services/payment/alipay/client.py`：
```python
"""Lazy singleton wrapper for alipay-sdk-python client."""
from functools import lru_cache

from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient

from configs import dify_config


def _read_pem(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # SDK expects key without header/footer
    return (
        content.replace("-----BEGIN RSA PRIVATE KEY-----", "")
        .replace("-----END RSA PRIVATE KEY-----", "")
        .replace("-----BEGIN PUBLIC KEY-----", "")
        .replace("-----END PUBLIC KEY-----", "")
        .replace("\n", "")
        .strip()
    )


@lru_cache(maxsize=1)
def get_alipay_client() -> DefaultAlipayClient:
    cfg = AlipayClientConfig()
    cfg.server_url = dify_config.ALIPAY_GATEWAY
    cfg.app_id = dify_config.ALIPAY_APP_ID
    cfg.app_private_key = _read_pem(dify_config.ALIPAY_APP_PRIVATE_KEY_PATH)
    cfg.alipay_public_key = _read_pem(dify_config.ALIPAY_PUBLIC_KEY_PATH)
    cfg.sign_type = dify_config.ALIPAY_SIGN_TYPE
    return DefaultAlipayClient(alipay_client_config=cfg)
```

`api/services/payment/alipay/provider.py`：
```python
"""Alipay implementation of PaymentProvider."""
import json
import logging
from decimal import Decimal

from alipay.aop.api.domain.AlipayTradePrecreateModel import AlipayTradePrecreateModel
from alipay.aop.api.request.AlipayTradePrecreateRequest import AlipayTradePrecreateRequest
from alipay.aop.api.request.AlipayTradeQueryRequest import AlipayTradeQueryRequest
from alipay.aop.api.domain.AlipayTradeQueryModel import AlipayTradeQueryModel

from configs import dify_config
from services.payment.alipay.client import get_alipay_client
from services.payment.base import (
    CreateOrderResult,
    NotifyPayload,
    ProviderOrderStatus,
)
from services.payment.exceptions import ProviderError

logger = logging.getLogger(__name__)


class AlipayProvider:
    name = "alipay"

    def create_qr_order(
        self, *, out_trade_no: str, amount_fen: int, subject: str, notify_url: str
    ) -> CreateOrderResult:
        model = AlipayTradePrecreateModel()
        model.out_trade_no = out_trade_no
        model.total_amount = f"{amount_fen / 100:.2f}"
        model.subject = subject

        req = AlipayTradePrecreateRequest(biz_model=model)
        req.notify_url = notify_url

        client = get_alipay_client()
        resp_str = client.execute(req)
        resp = json.loads(resp_str) if isinstance(resp_str, str) else resp_str
        if not resp.get("qr_code"):
            raise ProviderError(f"Alipay precreate failed: {resp}")
        return CreateOrderResult(qr_code=resp["qr_code"], raw_response=json.dumps(resp))

    def query_order(self, *, out_trade_no: str) -> ProviderOrderStatus:
        model = AlipayTradeQueryModel()
        model.out_trade_no = out_trade_no
        req = AlipayTradeQueryRequest(biz_model=model)
        client = get_alipay_client()
        resp_str = client.execute(req)
        resp = json.loads(resp_str) if isinstance(resp_str, str) else resp_str
        trade_status = resp.get("trade_status")
        paid = trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED")
        return ProviderOrderStatus(
            paid=paid,
            provider_trade_no=resp.get("trade_no"),
            paid_amount=Decimal(resp["total_amount"]) if resp.get("total_amount") else None,
        )

    def verify_notify(self, *, params: dict) -> bool:
        from alipay.aop.api.util.SignatureUtils import verify_with_rsa
        sign = params.pop("sign", None)
        sign_type = params.pop("sign_type", None)
        if not sign:
            return False
        from urllib.parse import quote_plus
        sorted_items = sorted((k, v) for k, v in params.items() if v is not None)
        unsigned = "&".join(f"{k}={v}" for k, v in sorted_items)
        # 复用 SDK 内部签名校验
        try:
            from services.payment.alipay.client import _read_pem
            public_key = _read_pem(dify_config.ALIPAY_PUBLIC_KEY_PATH)
            return verify_with_rsa(public_key, unsigned.encode("utf-8"), sign)
        except Exception:
            logger.exception("Alipay notify verify failed")
            return False

    def parse_notify(self, *, params: dict) -> NotifyPayload:
        return NotifyPayload(
            out_trade_no=params["out_trade_no"],
            provider_trade_no=params.get("trade_no", ""),
            paid_amount=Decimal(params["total_amount"]),
            trade_status=params.get("trade_status", ""),
            raw=params,
        )
```

**Step 4：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/services/payment/test_alipay_provider.py -v`
Expected: PASS

**Step 5：提交**

```bash
git add api/services/payment/alipay/ api/tests/unit_tests/services/payment/
git commit -m "feat: implement AlipayProvider (precreate, query, verify, parse)"
```

---

### Task 3.4：PaymentService 业务编排

**Files:**
- Create: `api/services/payment/service.py`
- Test: `api/tests/unit_tests/services/payment/test_payment_service.py`

**Step 1：写失败的测试**

```python
"""Tests for PaymentService order creation + idempotent notify."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.payment.service import PaymentService


@patch("services.payment.service.AlipayProvider")
@patch("services.payment.service.db")
def test_create_topup_order_inserts_pending(mock_db, mock_provider_cls):
    mock_provider = MagicMock()
    mock_provider.create_qr_order.return_value = MagicMock(
        qr_code="https://qr.alipay.com/abc", raw_response="{}"
    )
    mock_provider_cls.return_value = mock_provider

    order = PaymentService.create_topup_order(
        tenant_id="t1", account_id="a1",
        amount_yuan=Decimal("10.00"), client_ip="1.2.3.4",
    )
    assert order.amount_fen == 1000
    assert order.status == "pending"
    assert order.qr_code == "https://qr.alipay.com/abc"
    mock_db.session.commit.assert_called()


@patch("services.payment.service.PaymentAlertService")
@patch("services.payment.service.AlipayProvider")
@patch("services.payment.service.TenantBalanceService")
@patch("services.payment.service.db")
def test_handle_notify_idempotent(mock_db, mock_tb_svc, mock_provider_cls, mock_alert):
    """Notify on already-paid order is no-op, returns 'success'."""
    from models.creator import PaymentOrder, PaymentOrderStatus
    paid_order = PaymentOrder(
        provider="alipay", out_trade_no="o1",
        tenant_id="t1", account_id="a1",
        amount=Decimal("10"), amount_fen=1000, subject="x",
        status=PaymentOrderStatus.PAID.value,
    )
    mock_db.session.scalar.return_value = paid_order
    mock_provider = MagicMock()
    mock_provider.verify_notify.return_value = True
    mock_provider.parse_notify.return_value = MagicMock(
        out_trade_no="o1", provider_trade_no="t999",
        paid_amount=Decimal("10"), trade_status="TRADE_SUCCESS",
        raw={"app_id": "myapp"},
    )
    mock_provider_cls.return_value = mock_provider

    with patch("services.payment.service.dify_config") as cfg:
        cfg.ALIPAY_APP_ID = "myapp"
        result = PaymentService.handle_alipay_notify({"out_trade_no": "o1"})
    assert result == "success"
    # no balance change since already paid
    mock_tb_svc.get_or_create.assert_not_called()
```

**Step 2：跑确认失败**

Run: `cd api && uv run pytest tests/unit_tests/services/payment/test_payment_service.py -v`
Expected: ImportError

**Step 3：实现 PaymentService**

`api/services/payment/service.py`：
```python
"""Payment business orchestration."""
import logging
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from configs import dify_config
from extensions.ext_database import db
from libs.helper import RateLimiter
from models import TenantAccountJoin
from models.creator import (
    BillingRecord,
    BillingRecordType,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentProviderName,
)
from services.payment.alipay.provider import AlipayProvider
from services.payment.alerts import PaymentAlertService
from services.payment.exceptions import OrderNotFound, ProviderError, SignatureInvalid
from services.user_billing_service import UserBillingService
from services.wallet.allocation_service import AllocationService
from services.wallet.tenant_balance_service import TenantBalanceService

logger = logging.getLogger(__name__)

_create_order_rate_limiter = RateLimiter("payment_create_order", 5, 60)


def _generate_out_trade_no() -> str:
    return f"DZ{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(6)}"


class PaymentService:
    @classmethod
    def create_topup_order(
        cls, *, tenant_id: str, account_id: str,
        amount_yuan: Decimal, client_ip: str,
        provider: str = PaymentProviderName.ALIPAY.value,
    ) -> PaymentOrder:
        if amount_yuan <= 0:
            raise ValueError("amount must be positive")
        amount_fen = int((amount_yuan * 100).quantize(Decimal("1")))
        if amount_fen < dify_config.ALIPAY_MIN_AMOUNT_FEN:
            raise ValueError(f"amount must be at least {dify_config.ALIPAY_MIN_AMOUNT_FEN/100:.2f} yuan")

        if _create_order_rate_limiter.is_rate_limited(account_id):
            raise ProviderError("RATE_LIMITED")
        _create_order_rate_limiter.increment_rate_limit(account_id)

        out_trade_no = _generate_out_trade_no()
        expires_at = datetime.utcnow() + timedelta(minutes=dify_config.ALIPAY_ORDER_TIMEOUT_MIN)
        order = PaymentOrder(
            provider=provider, out_trade_no=out_trade_no,
            tenant_id=tenant_id, account_id=account_id,
            amount=amount_yuan, amount_fen=amount_fen,
            subject=f"Workspace top-up {tenant_id[:8]}",
            status=PaymentOrderStatus.PENDING.value,
            expires_at=expires_at, client_ip=client_ip,
        )
        db.session.add(order)
        db.session.commit()

        provider_inst = AlipayProvider() if provider == "alipay" else None
        if not provider_inst:
            raise ProviderError(f"Unknown provider: {provider}")

        try:
            result = provider_inst.create_qr_order(
                out_trade_no=out_trade_no, amount_fen=amount_fen,
                subject=order.subject, notify_url=dify_config.ALIPAY_NOTIFY_URL,
            )
        except Exception as e:
            order.status = PaymentOrderStatus.FAILED.value
            db.session.commit()
            raise ProviderError(str(e))

        order.qr_code = result.qr_code
        order.prepay_raw = result.raw_response
        db.session.commit()
        return order

    @classmethod
    def get_order(cls, *, order_id: str) -> PaymentOrder:
        order = db.session.scalar(select(PaymentOrder).where(PaymentOrder.id == order_id))
        if not order:
            raise OrderNotFound(order_id)
        return order

    @classmethod
    def handle_alipay_notify(cls, params: dict) -> str:
        """Process Alipay async notify. Returns 'success' or 'fail'."""
        provider = AlipayProvider()
        if not provider.verify_notify(params=dict(params)):
            logger.warning("Alipay notify signature invalid: %s", params.get("out_trade_no"))
            return "fail"

        payload = provider.parse_notify(params=params)

        if payload.raw.get("app_id") != dify_config.ALIPAY_APP_ID:
            logger.warning("Alipay notify app_id mismatch")
            return "fail"

        if payload.trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            return "success"  # ignore other statuses

        order = db.session.scalar(
            select(PaymentOrder).where(PaymentOrder.out_trade_no == payload.out_trade_no).with_for_update()
        )
        if not order:
            return "fail"

        order.notify_raw = str(payload.raw)
        if order.status == PaymentOrderStatus.PAID.value:
            db.session.commit()
            return "success"  # idempotent

        if payload.paid_amount != order.amount:
            logger.error("Amount mismatch: order=%s notify=%s", order.amount, payload.paid_amount)
            return "fail"

        # Mark paid + ledger + tenant balance
        order.status = PaymentOrderStatus.PAID.value
        order.paid_at = datetime.utcnow()
        order.provider_trade_no = payload.provider_trade_no

        tenant_balance = TenantBalanceService.get_or_create(order.tenant_id)
        tenant_balance.balance += order.amount
        tenant_balance.total_topup += order.amount

        topup_record = BillingRecord(
            account_id=order.account_id, tenant_id=order.tenant_id,
            amount=order.amount, record_type=BillingRecordType.TOPUP.value,
            scope="tenant", description=f"Alipay top-up {order.out_trade_no}",
        )
        db.session.add_all([order, tenant_balance, topup_record])
        db.session.commit()

        # Auto-allocate to owner if personal tenant (single-member)
        cls._auto_allocate_personal_tenant(order)

        # Large amount alert (non-blocking)
        try:
            PaymentAlertService.check_and_notify(order)
        except Exception:
            logger.exception("Large amount alert failed")

        return "success"

    @classmethod
    def _auto_allocate_personal_tenant(cls, order: PaymentOrder) -> None:
        member_count = db.session.scalar(
            select(db.func.count()).select_from(TenantAccountJoin)
            .where(TenantAccountJoin.tenant_id == order.tenant_id)
        )
        if member_count == 1:
            try:
                AllocationService.allocate(
                    tenant_id=order.tenant_id, account_id=order.account_id,
                    operator_id=order.account_id, amount=order.amount,
                    description="Auto-allocate (personal workspace)",
                )
            except Exception:
                logger.exception("Auto-allocate personal tenant failed")

    @classmethod
    def close_expired_orders(cls) -> int:
        now = datetime.utcnow()
        orders = list(db.session.scalars(
            select(PaymentOrder).where(
                PaymentOrder.status == PaymentOrderStatus.PENDING.value,
                PaymentOrder.expires_at < now,
            )
        ).all())
        for o in orders:
            o.status = PaymentOrderStatus.CLOSED.value
            db.session.add(o)
        db.session.commit()
        return len(orders)
```

**Step 4：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/services/payment/test_payment_service.py -v`
Expected: PASS

**Step 5：提交**

```bash
git add api/services/payment/service.py api/tests/unit_tests/services/payment/test_payment_service.py
git commit -m "feat: PaymentService for order creation + idempotent notify handling"
```

---

### Task 3.5：PaymentAlertService（大额告警）

**Files:**
- Create: `api/services/payment/alerts.py`
- Test: `api/tests/unit_tests/services/payment/test_alerts.py`

**Step 1：写失败的测试**

```python
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.payment.alerts import PaymentAlertService


@patch("services.payment.alerts.dify_config")
@patch("services.payment.alerts.logger")
def test_below_threshold_no_alert(mock_logger, mock_cfg):
    mock_cfg.ALIPAY_LARGE_AMOUNT_THRESHOLD = 5000
    order = MagicMock(amount=Decimal("100"))
    PaymentAlertService.check_and_notify(order)
    mock_logger.warning.assert_not_called()


@patch("services.payment.alerts.dify_config")
@patch("services.payment.alerts.logger")
def test_above_threshold_logs_alert(mock_logger, mock_cfg):
    mock_cfg.ALIPAY_LARGE_AMOUNT_THRESHOLD = 5000
    order = MagicMock(amount=Decimal("10000"), id="o1", out_trade_no="x", tenant_id="t1")
    PaymentAlertService.check_and_notify(order)
    mock_logger.warning.assert_called()
```

**Step 2：跑确认失败**

Run: `cd api && uv run pytest tests/unit_tests/services/payment/test_alerts.py -v`
Expected: ImportError

**Step 3：实现**

`api/services/payment/alerts.py`：
```python
"""Large top-up amount alerts."""
import logging
from decimal import Decimal

from configs import dify_config

logger = logging.getLogger(__name__)


class PaymentAlertService:
    @classmethod
    def check_and_notify(cls, order) -> None:
        threshold = Decimal(dify_config.ALIPAY_LARGE_AMOUNT_THRESHOLD)
        if order.amount >= threshold:
            logger.warning(
                "LARGE_TOPUP_ALERT: tenant=%s order=%s amount=%s",
                order.tenant_id, order.out_trade_no, order.amount,
            )
            # TODO: hook into existing email/notification system if needed
```

**Step 4：跑测试**

Run: `cd api && uv run pytest tests/unit_tests/services/payment/test_alerts.py -v`
Expected: PASS

**Step 5：提交**

```bash
git add api/services/payment/alerts.py api/tests/unit_tests/services/payment/test_alerts.py
git commit -m "feat: log-based large top-up alert"
```

---

### Task 3.6：定时任务 close_expired_orders

**Files:**
- Create: `api/schedule/payment_tasks.py`
- Modify: `api/schedule/__init__.py`（如有 beat 配置）

**Step 1：实现 task**

```python
"""Celery scheduled tasks for payment orders."""
import logging

import click
from celery import shared_task

from services.payment.service import PaymentService

logger = logging.getLogger(__name__)


@shared_task(queue="dataset")
def close_expired_payment_orders():
    """Close pending PaymentOrder rows past expires_at. Runs every 5 minutes."""
    click.echo(click.style("Start close expired payment orders.", fg="green"))
    try:
        n = PaymentService.close_expired_orders()
        click.echo(click.style(f"Closed {n} expired payment orders.", fg="green"))
    except Exception:
        logger.exception("close_expired_payment_orders failed")
```

**Step 2：注册到 beat（如果有 schedule 配置）**

Run: `grep -rn "beat_schedule\|schedule" api/schedule/__init__.py api/configs/*.py 2>/dev/null | head -20`

如有 beat schedule 配置，加：
```python
"close-expired-payment-orders": {
    "task": "schedule.payment_tasks.close_expired_payment_orders",
    "schedule": crontab(minute="*/5"),
},
```
否则跳过此步（沿用现有 schedule 调用方式）。

**Step 3：提交**

```bash
git add api/schedule/payment_tasks.py
git commit -m "feat: scheduled task to close expired payment orders"
```

---

## Phase 4：API 端点

### Task 4.1：充值订单 API（创建、查询）

**Files:**
- Create: `api/controllers/console/billing/payment.py`
- Modify: `api/controllers/console/__init__.py`（注册路由）

**Step 1：实现 Resource**

```python
"""Payment / top-up endpoints."""
from decimal import Decimal, InvalidOperation

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from services.billing_service import BillingService
from services.payment.exceptions import OrderNotFound, ProviderError
from services.payment.service import PaymentService


def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


@console_ns.route("/billing/topup/orders")
class TopupOrdersApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            BillingService.is_tenant_owner_or_admin(current_user)
        except ValueError:
            raise Forbidden("NOT_TENANT_ADMIN")

        payload = request.get_json() or {}
        provider = payload.get("provider", "alipay")
        try:
            amount = Decimal(str(payload.get("amount", "")))
        except (InvalidOperation, TypeError):
            raise BadRequest("INVALID_AMOUNT")

        try:
            order = PaymentService.create_topup_order(
                tenant_id=current_tenant_id, account_id=current_user.id,
                amount_yuan=amount, client_ip=_client_ip(), provider=provider,
            )
        except ValueError as e:
            raise BadRequest(str(e))
        except ProviderError as e:
            if str(e) == "RATE_LIMITED":
                from werkzeug.exceptions import TooManyRequests
                raise TooManyRequests("RATE_LIMITED")
            raise
        return order.to_dict(), 201


@console_ns.route("/billing/topup/orders/<string:order_id>")
class TopupOrderDetailApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, order_id: str):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            order = PaymentService.get_order(order_id=order_id)
        except OrderNotFound:
            raise NotFound()
        if order.tenant_id != current_tenant_id:
            raise Forbidden()
        return order.to_dict()
```

**Step 2：注册路由**

确认 `api/controllers/console/billing/__init__.py` 是否已 import payment 模块。如未自动 discover，手动加 `from . import payment`。

**Step 3：手动测试（可选，跳过严格 TDD 因为是 IO-heavy 控制器）**

Run: `cd api && uv run python -c "from controllers.console.billing import payment; print('OK')"`
Expected: `OK`

**Step 4：提交**

```bash
git add api/controllers/console/billing/payment.py
git commit -m "feat: console API for creating and querying top-up orders"
```

---

### Task 4.2：支付宝异步通知 API

**Files:**
- Modify: `api/controllers/console/billing/payment.py` (追加)

**Step 1：在文件末尾加 notify endpoint**

```python
@console_ns.route("/billing/alipay/notify")
class AlipayNotifyApi(Resource):
    """Public endpoint for Alipay async notification.

    NO auth: relies on signature verification within PaymentService.
    Must return literal 'success' or 'fail' as plain text.
    """

    def post(self):
        from flask import Response
        params = request.form.to_dict()
        result = PaymentService.handle_alipay_notify(params)
        return Response(result, mimetype="text/plain")
```

**Step 2：手动验证**

Run: `cd api && uv run python -c "from controllers.console.billing.payment import AlipayNotifyApi; print('OK')"`
Expected: `OK`

**Step 3：提交**

```bash
git add api/controllers/console/billing/payment.py
git commit -m "feat: alipay async notify endpoint"
```

---

### Task 4.3：Tenant 钱包 API（查询、成员列表、分配）

**Files:**
- Create: `api/controllers/console/billing/tenant_wallet.py`

**Step 1：实现**

```python
"""Tenant wallet & allocation endpoints."""
from decimal import Decimal, InvalidOperation

from flask import request
from flask_restx import Resource
from sqlalchemy import select
from werkzeug.exceptions import BadRequest, Forbidden

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from extensions.ext_database import db
from libs.login import current_account_with_tenant, login_required
from models import Account, TenantAccountJoin
from models.creator import AllocationRecord, UserBalance
from services.billing_service import BillingService
from services.wallet.allocation_service import AllocationService
from services.wallet.exceptions import (
    InsufficientMemberBalance,
    InsufficientTenantBalance,
    NotTenantMember,
)
from services.wallet.tenant_balance_service import TenantBalanceService


@console_ns.route("/billing/tenant/wallet")
class TenantWalletApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        _, current_tenant_id = current_account_with_tenant()
        b = TenantBalanceService.get_or_create(current_tenant_id)
        return {
            "tenant_id": b.tenant_id,
            "balance": str(b.balance),
            "locked": str(b.locked),
            "total": str(b.total),
            "total_topup": str(b.total_topup),
            "currency": b.currency,
        }


@console_ns.route("/billing/tenant/members")
class TenantMembersApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            BillingService.is_tenant_owner_or_admin(current_user)
        except ValueError:
            raise Forbidden("NOT_TENANT_ADMIN")

        rows = db.session.execute(
            select(Account, UserBalance, TenantAccountJoin)
            .join(TenantAccountJoin, TenantAccountJoin.account_id == Account.id)
            .outerjoin(UserBalance, UserBalance.account_id == Account.id)
            .where(TenantAccountJoin.tenant_id == current_tenant_id)
        ).all()
        return {
            "data": [
                {
                    "account_id": acc.id,
                    "name": acc.name,
                    "email": acc.email,
                    "role": tj.role,
                    "balance": str(ub.balance) if ub else "0",
                    "currency": ub.currency if ub else "CNY",
                }
                for acc, ub, tj in rows
            ]
        }


@console_ns.route("/billing/tenant/allocations")
class TenantAllocationsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            BillingService.is_tenant_owner_or_admin(current_user)
        except ValueError:
            raise Forbidden("NOT_TENANT_ADMIN")

        payload = request.get_json() or {}
        target_account_id = payload.get("account_id")
        try:
            amount = Decimal(str(payload.get("amount", "")))
        except (InvalidOperation, TypeError):
            raise BadRequest("INVALID_AMOUNT")
        description = payload.get("description")

        if not target_account_id:
            raise BadRequest("account_id required")

        try:
            record = AllocationService.allocate(
                tenant_id=current_tenant_id, account_id=target_account_id,
                operator_id=current_user.id, amount=amount, description=description,
            )
        except NotTenantMember:
            raise BadRequest("NOT_TENANT_MEMBER")
        except InsufficientTenantBalance:
            raise BadRequest("ALLOCATION_EXCEEDS_BALANCE")
        except InsufficientMemberBalance:
            raise BadRequest("RECLAIM_EXCEEDS_MEMBER_BALANCE")

        return record.to_dict(), 201

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            BillingService.is_tenant_owner_or_admin(current_user)
        except ValueError:
            raise Forbidden("NOT_TENANT_ADMIN")

        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))
        records = list(db.session.scalars(
            select(AllocationRecord).where(AllocationRecord.tenant_id == current_tenant_id)
            .order_by(AllocationRecord.created_at.desc()).limit(limit).offset(offset)
        ).all())
        return {"data": [r.to_dict() for r in records], "limit": limit, "offset": offset}
```

**Step 2：验证 import**

Run: `cd api && uv run python -c "from controllers.console.billing import tenant_wallet; print('OK')"`
Expected: `OK`

**Step 3：提交**

```bash
git add api/controllers/console/billing/tenant_wallet.py
git commit -m "feat: tenant wallet + members + allocation API endpoints"
```

---

### Task 4.4：阻塞 workflow 在余额不足时（INSUFFICIENT_USER_BUDGET）

**Files:**
- Modify: `api/controllers/console/explore/completion.py` (line ~56 处)

**Step 1：把现有 `check_balance_positive` 调用切换到 `check_can_run`**

打开 `completion.py`，找到第 56 行附近：
```python
return bool(marketplace_entry) and not UserBillingService.check_balance_positive(account.id)
```

替换为：
```python
if not bool(marketplace_entry):
    return False
ok, _code = UserBillingService.check_can_run(account.id, current_tenant_id)
return not ok
```

确保 `current_tenant_id` 在该 scope 内可用（如不可用从 `current_account_with_tenant()` 获取）。

**Step 2：手动验证**

Run: `cd api && uv run python -c "from controllers.console.explore import completion; print('OK')"`
Expected: `OK`

**Step 3：提交**

```bash
git add api/controllers/console/explore/completion.py
git commit -m "refactor: use check_can_run for tenant-aware balance gate"
```

---

## Phase 5：前端

### Task 5.1：API service 层

**Files:**
- Create: `web/service/billing.ts`
- Create: `web/service/use-billing.ts`

**Step 1：实现 fetch 封装**

`web/service/billing.ts`：
```typescript
import { get, post } from './base'

export type TenantWallet = {
  tenant_id: string
  balance: string
  locked: string
  total: string
  total_topup: string
  currency: string
}

export type TopupOrder = {
  id: string
  out_trade_no: string
  status: 'pending' | 'paid' | 'closed' | 'failed'
  amount: string
  qr_code: string | null
  paid_at: string | null
  expires_at: string | null
}

export type TenantMember = {
  account_id: string
  name: string
  email: string
  role: string
  balance: string
  currency: string
}

export const fetchTenantWallet = (): Promise<TenantWallet> =>
  get('/billing/tenant/wallet')

export const fetchTenantMembers = (): Promise<{ data: TenantMember[] }> =>
  get('/billing/tenant/members')

export const createTopupOrder = (amount: string, provider = 'alipay'): Promise<TopupOrder> =>
  post('/billing/topup/orders', { body: { amount, provider } })

export const fetchTopupOrder = (orderId: string): Promise<TopupOrder> =>
  get(`/billing/topup/orders/${orderId}`)

export const allocate = (accountId: string, amount: string, description?: string) =>
  post('/billing/tenant/allocations', { body: { account_id: accountId, amount, description } })
```

**Step 2：实现 React Query hooks**

`web/service/use-billing.ts`：
```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './billing'

const KEY_TENANT_WALLET = ['billing', 'tenant-wallet']
const KEY_MEMBERS = ['billing', 'tenant-members']

export const useTenantWallet = () =>
  useQuery({ queryKey: KEY_TENANT_WALLET, queryFn: api.fetchTenantWallet })

export const useTenantMembers = () =>
  useQuery({ queryKey: KEY_MEMBERS, queryFn: api.fetchTenantMembers })

export const useCreateTopupOrder = () =>
  useMutation({ mutationFn: ({ amount }: { amount: string }) => api.createTopupOrder(amount) })

export const useTopupOrder = (orderId: string | null, enabled = true) =>
  useQuery({
    queryKey: ['billing', 'order', orderId],
    queryFn: () => api.fetchTopupOrder(orderId!),
    enabled: enabled && !!orderId,
    refetchInterval: (q) => {
      const data = q.state.data as api.TopupOrder | undefined
      return data && data.status === 'pending' ? 2000 : false
    },
  })

export const useAllocate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ accountId, amount, description }: { accountId: string; amount: string; description?: string }) =>
      api.allocate(accountId, amount, description),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_TENANT_WALLET })
      qc.invalidateQueries({ queryKey: KEY_MEMBERS })
    },
  })
}
```

**Step 3：类型检查**

Run: `cd web && pnpm type-check:tsgo`
Expected: 无新增类型错误

**Step 4：提交**

```bash
git add web/service/billing.ts web/service/use-billing.ts
git commit -m "feat: billing API client + React Query hooks"
```

---

### Task 5.2：i18n 文案

**Files:**
- Create: `web/i18n/en-US/billing.ts`
- Create: `web/i18n/zh-Hans/billing.ts`
- Modify: `web/i18n/index.ts`（加 namespace）

**Step 1：创建中文文案**

`web/i18n/zh-Hans/billing.ts`：
```typescript
const translation = {
  wallet: {
    title: '工作空间钱包',
    balance: '可分配余额',
    locked: '已分配',
    total: '总计',
    totalTopup: '累计充值',
    currency: '货币',
    topup: '充值',
    insufficient: '余额不足',
  },
  topup: {
    title: '充值',
    amount: '充值金额（元）',
    provider: '支付方式',
    alipay: '支付宝',
    qrcodeTip: '请使用支付宝扫码支付',
    paid: '充值成功',
    expired: '订单已过期，请重新发起',
    failed: '订单失败',
    invalidAmount: '请输入有效的金额',
    submit: '生成支付二维码',
    rateLimited: '操作过于频繁，请稍后再试',
  },
  allocation: {
    title: '成员额度',
    member: '成员',
    role: '角色',
    balance: '可用额度',
    allocate: '分配',
    reclaim: '回收',
    amount: '金额',
    note: '备注',
    submit: '确认',
    exceedsBalance: '分配金额超过工作空间可用余额',
    exceedsMemberBalance: '回收金额超过成员当前余额',
    notMember: '该账户不是工作空间成员',
  },
  errors: {
    notTenantAdmin: '仅工作空间所有者或管理员可执行此操作',
    insufficientUserBudget: '您的可用额度已用完，请联系空间管理员分配',
    insufficientTenantBalance: '工作空间余额不足，请管理员充值',
  },
}

export default translation
```

**Step 2：创建英文文案**

`web/i18n/en-US/billing.ts`：照抄结构，文案改成英文。

**Step 3：注册 namespace**

打开 `web/i18n/index.ts`，找到 namespace 列表，加上 `'billing'`。

**Step 4：提交**

```bash
git add web/i18n/{en-US,zh-Hans}/billing.ts web/i18n/index.ts
git commit -m "feat: add billing i18n namespace (zh-Hans + en-US)"
```

---

### Task 5.3：充值弹窗组件（核心 UX）

**Files:**
- Create: `web/app/(commonLayout)/billing/_components/topup-modal.tsx`
- Create: `web/app/(commonLayout)/billing/_components/topup-qrcode.tsx`

**Step 1：实现二维码组件**

`web/app/(commonLayout)/billing/_components/topup-qrcode.tsx`：
```typescript
'use client'
import { QRCodeSVG } from 'qrcode.react'
import { useTranslation } from 'react-i18next'
import { useTopupOrder } from '@/service/use-billing'

type Props = {
  orderId: string
  onPaid: () => void
  onExpired: () => void
}

const TopupQRCode = ({ orderId, onPaid, onExpired }: Props) => {
  const { t } = useTranslation()
  const { data: order } = useTopupOrder(orderId)

  if (!order)
    return <div className="py-8 text-center">…</div>

  if (order.status === 'paid') {
    onPaid()
    return <div className="py-8 text-center text-green-600">{t('billing.topup.paid')}</div>
  }
  if (order.status === 'closed' || order.status === 'failed') {
    onExpired()
    return <div className="py-8 text-center text-red-600">{t('billing.topup.expired')}</div>
  }

  return (
    <div className="flex flex-col items-center gap-3 py-4">
      <QRCodeSVG value={order.qr_code || ''} size={220} level="M" />
      <p className="text-sm text-gray-600">{t('billing.topup.qrcodeTip')}</p>
      <p className="text-xl font-semibold">¥ {order.amount}</p>
    </div>
  )
}

export default TopupQRCode
```

**Step 2：实现弹窗**

`topup-modal.tsx`：
```typescript
'use client'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import Modal from '@/app/components/base/modal'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { useCreateTopupOrder } from '@/service/use-billing'
import TopupQRCode from './topup-qrcode'

type Props = {
  open: boolean
  onClose: () => void
}

const TopupModal = ({ open, onClose }: Props) => {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [amount, setAmount] = useState('100')
  const [orderId, setOrderId] = useState<string | null>(null)
  const createOrder = useCreateTopupOrder()

  const handleSubmit = () => {
    if (!amount || Number(amount) <= 0)
      return
    createOrder.mutate({ amount }, { onSuccess: (o) => setOrderId(o.id) })
  }

  const handlePaid = () => {
    qc.invalidateQueries({ queryKey: ['billing', 'tenant-wallet'] })
    setTimeout(onClose, 1500)
  }

  return (
    <Modal isShow={open} onClose={onClose} title={t('billing.topup.title')}>
      {!orderId
        ? (
          <div className="space-y-4 p-4">
            <label className="block text-sm">{t('billing.topup.amount')}</label>
            <Input value={amount} onChange={e => setAmount(e.target.value)} type="number" />
            <Button variant="primary" onClick={handleSubmit} disabled={createOrder.isPending}>
              {t('billing.topup.submit')}
            </Button>
          </div>
        )
        : (
          <TopupQRCode orderId={orderId} onPaid={handlePaid} onExpired={() => setOrderId(null)} />
        )}
    </Modal>
  )
}

export default TopupModal
```

**Step 3：类型检查**

Run: `cd web && pnpm type-check:tsgo 2>&1 | grep "billing/_components" | head -10`
Expected: 无错误

**Step 4：提交**

```bash
git add 'web/app/(commonLayout)/billing/'
git commit -m "feat: top-up modal with QR code polling"
```

---

### Task 5.4：钱包页面 + 余额卡 + 成员分配表

**Files:**
- Create: `web/app/(commonLayout)/billing/page.tsx`
- Create: `web/app/(commonLayout)/billing/_components/wallet-card.tsx`
- Create: `web/app/(commonLayout)/billing/_components/allocation-table.tsx`
- Create: `web/app/(commonLayout)/billing/_components/allocation-modal.tsx`

**Step 1：wallet-card.tsx**

```typescript
'use client'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import { useTenantWallet } from '@/service/use-billing'

const WalletCard = ({ onTopup }: { onTopup: () => void }) => {
  const { t } = useTranslation()
  const { data: wallet } = useTenantWallet()
  if (!wallet)
    return null
  return (
    <div className="rounded-xl border border-gray-200 bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="text-sm text-gray-600">{t('billing.wallet.title')}</div>
      <div className="mt-2 text-4xl font-bold text-gray-900">¥ {wallet.balance}</div>
      <div className="mt-1 text-sm text-gray-600">
        {t('billing.wallet.locked')}: ¥ {wallet.locked} · {t('billing.wallet.totalTopup')}: ¥ {wallet.total_topup}
      </div>
      <Button variant="primary" className="mt-4" onClick={onTopup}>
        {t('billing.wallet.topup')}
      </Button>
    </div>
  )
}
export default WalletCard
```

**Step 2：allocation-modal.tsx**

```typescript
'use client'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Toast from '@/app/components/base/toast'
import Modal from '@/app/components/base/modal'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { useAllocate } from '@/service/use-billing'

type Props = {
  open: boolean
  onClose: () => void
  member: { account_id: string; name: string } | null
}

const AllocationModal = ({ open, onClose, member }: Props) => {
  const { t } = useTranslation()
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const allocate = useAllocate()

  const handleSubmit = (sign: 1 | -1) => {
    if (!member || !amount)
      return
    const signed = (Number(amount) * sign).toString()
    allocate.mutate(
      { accountId: member.account_id, amount: signed, description: note },
      {
        onSuccess: () => {
          Toast.notify({ type: 'success', message: t('common.success') })
          onClose()
        },
        onError: (err: any) => {
          const code = err?.message || 'unknown'
          Toast.notify({ type: 'error', message: t(`billing.allocation.${code}`, code) })
        },
      },
    )
  }

  return (
    <Modal isShow={open} onClose={onClose} title={`${t('billing.allocation.title')} - ${member?.name ?? ''}`}>
      <div className="space-y-4 p-4">
        <Input type="number" placeholder={t('billing.allocation.amount')} value={amount} onChange={e => setAmount(e.target.value)} />
        <Input placeholder={t('billing.allocation.note')} value={note} onChange={e => setNote(e.target.value)} />
        <div className="flex gap-2">
          <Button variant="primary" onClick={() => handleSubmit(1)}>{t('billing.allocation.allocate')}</Button>
          <Button variant="secondary" onClick={() => handleSubmit(-1)}>{t('billing.allocation.reclaim')}</Button>
        </div>
      </div>
    </Modal>
  )
}
export default AllocationModal
```

**Step 3：allocation-table.tsx**

```typescript
'use client'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import { useTenantMembers } from '@/service/use-billing'
import AllocationModal from './allocation-modal'

const AllocationTable = () => {
  const { t } = useTranslation()
  const { data } = useTenantMembers()
  const [target, setTarget] = useState<{ account_id: string; name: string } | null>(null)

  return (
    <div className="rounded-lg border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left">
          <tr>
            <th className="p-3">{t('billing.allocation.member')}</th>
            <th className="p-3">{t('billing.allocation.role')}</th>
            <th className="p-3">{t('billing.allocation.balance')}</th>
            <th className="p-3"></th>
          </tr>
        </thead>
        <tbody>
          {data?.data.map(m => (
            <tr key={m.account_id} className="border-t">
              <td className="p-3">
                <div className="font-medium">{m.name}</div>
                <div className="text-xs text-gray-500">{m.email}</div>
              </td>
              <td className="p-3">{m.role}</td>
              <td className="p-3">¥ {m.balance}</td>
              <td className="p-3">
                <Button onClick={() => setTarget({ account_id: m.account_id, name: m.name })}>
                  {t('billing.allocation.allocate')}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <AllocationModal open={!!target} onClose={() => setTarget(null)} member={target} />
    </div>
  )
}
export default AllocationTable
```

**Step 4：page.tsx**

```typescript
'use client'
import { useState } from 'react'
import WalletCard from './_components/wallet-card'
import AllocationTable from './_components/allocation-table'
import TopupModal from './_components/topup-modal'

const BillingPage = () => {
  const [topupOpen, setTopupOpen] = useState(false)
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <WalletCard onTopup={() => setTopupOpen(true)} />
      <AllocationTable />
      <TopupModal open={topupOpen} onClose={() => setTopupOpen(false)} />
    </div>
  )
}
export default BillingPage
```

**Step 5：类型检查 + 提交**

Run: `cd web && pnpm type-check:tsgo 2>&1 | grep "billing" | head -10`
Expected: 无错误

```bash
git add 'web/app/(commonLayout)/billing/'
git commit -m "feat: billing page with wallet card + allocation table"
```

---

## Phase 6：联调 + 收尾

### Task 6.1：跑全部新增测试

Run: `cd api && uv run pytest tests/unit_tests/services/wallet/ tests/unit_tests/services/payment/ tests/unit_tests/models/test_payment_models.py -v`
Expected: 全部 PASS

Run: `cd web && pnpm lint:fix && pnpm type-check:tsgo`
Expected: 无错误

如有失败，回到对应 Task 修复后重新跑。

---

### Task 6.2：撰写 docs/CODEMAPS（如该项目用 codemaps）

Run: `ls docs/CODEMAPS 2>/dev/null && echo "exists" || echo "skip"`

如存在，按现有约定补充 payment/wallet 模块条目；不存在则跳过。

---

### Task 6.3：手动联调清单

部署到测试环境后手动验证：

- [ ] 配置 ALIPAY_USE_SANDBOX=true + 沙箱 APPID
- [ ] 创建充值订单 → 二维码可显示
- [ ] 沙箱扫码支付 → 回调成功 → 钱包余额 +N
- [ ] 重复 POST 通知 → 仍只入账一次（幂等）
- [ ] 个人 Tenant 充值 → owner UserBalance 自动 +N
- [ ] owner 给成员分配 → 成员钱包变更，不变式成立
- [ ] 成员 UserBalance=0 时跑 workflow → 返回 INSUFFICIENT_USER_BUDGET
- [ ] 15 分钟未支付 → 定时任务关闭订单

---

### Task 6.4：创建 PR

Run:
```bash
git push -u origin feat/alipay-topup-wallet
gh pr create --title "feat: Alipay top-up + workspace two-tier wallet" \
  --body "$(cat <<'EOF'
## Summary
- Two-tier wallet: TenantBalance + UserBalance
- Alipay precreate (扫码支付) integration with PaymentProvider abstraction
- Strict budget allocation (owner -> member, signed amount, not over-allocatable)
- Dual deduction on workflow run (tenant.locked + user.balance)
- Idempotent async notify with signature + amount + app_id verification
- Large amount alert + scheduled order expiration
- Frontend billing page with QR-code top-up modal

## Test plan
- [ ] All new unit tests pass: `pytest tests/unit_tests/services/{wallet,payment}/`
- [ ] Sandbox alipay end-to-end (see Task 6.3)
- [ ] Migration + data backfill verified on staging DB
- [ ] Frontend type-check + lint clean
EOF
)"
```

---

## 验收标准

- 所有新单元测试通过，覆盖率 ≥ 80%
- 沙箱端到端联调验收清单全部通过
- `Σ UserBalance.balance == TenantBalance.locked` 不变式成立
- 回调幂等：同一通知 10 次重发只入账 1 次
- 老数据迁移完成，迁移前后总余额一致

---

**实施计划版本**：v1.0
**关联设计稿**：`docs/plans/2026-04-14-alipay-topup-design.md`
