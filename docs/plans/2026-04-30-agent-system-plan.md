# 代理商体系实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 [docs/plans/2026-04-30-agent-system-design.md](2026-04-30-agent-system-design.md) 的设计落地为可上线的代理商体系。

**Architecture:** 后端遵循 DDD/Clean Architecture(model → service → controller),前端沿用 Next.js App Router + 路由组 + oRPC contract + TanStack Query。所有改动在 `feat/agent-system` 分支。

**Tech Stack:** Python 3.11 + Flask + SQLAlchemy + Alembic(后端);TypeScript + Next.js + React + Vitest + RTL(前端);PostgreSQL;Celery + Redis(异步任务)

**Working Directory:** 所有命令在 worktree 内执行。`cd /Users/guijinhao/Documents/zhongda/dify/.worktrees/agent-system`

**TDD 强制要求:** 每个 task 严格按 RED → GREEN → COMMIT 顺序。先写测试、确认失败、再写实现、确认通过、再 commit。绝不允许在没有失败测试的情况下写实现代码。

**执行顺序:** Phase 0 → 1 → 2 → 3 必须严格顺序(后端依赖链);Phase 4 依赖 Phase 2;Phase 5 依赖 Phase 4;Phase 6(E2E)最后做。

---

## 阶段总览

| Phase | 内容 | Tasks | 关键依赖 |
|-------|------|------|------|
| 0 | 数据模型 + alembic 迁移 | 8 | 无 |
| 1 | 后端 6 个 service + 领域异常 | 18 | Phase 0 |
| 2 | 后端 11 个 API 端点(代理控制台 6 + 后台超管 5) | 14 | Phase 1 |
| 3 | 后端清理 + Celery 改造 + 注册接口清理 + 新增 expiry task | 10 | Phase 2 |
| 4 | 前端 contract + 代理控制台 4 页 + BindConfirmDialog + i18n | 16 | Phase 2 |
| 5 | 前端清理 + 后台超管 5 页 + 登录 redirect + signup/signin 改造 | 12 | Phase 4 |
| 6 | E2E 关键路径 4 个 | 5 | 全部完成 |

合计 **83 tasks**。

---

# Phase 0:数据模型与迁移

## Task 0.1:Agent / AgentWallet / RebindRequest / WithdrawalRequest 模型类

**Files:**
- Create: `api/models/agent.py`
- Create: `api/tests/unit_tests/models/test_agent_models.py`

**Step 1: 写失败测试**

```python
# api/tests/unit_tests/models/test_agent_models.py
"""Sanity tests for agent models — verify columns + import. Business
behaviour is covered in service-level tests in Phase 1.
"""


def test_agent_model_has_required_columns():
    from models.agent import Agent
    cols = {c.name for c in Agent.__table__.columns}
    for required in {
        "id", "account_id", "name", "status", "rebate_rate",
        "level", "region_province", "region_city",
        "contact_phone", "notes", "signed_at", "expires_at",
        "created_by", "created_at", "updated_at",
    }:
        assert required in cols, f"Agent missing column {required}"


def test_agent_wallet_has_required_columns():
    from models.agent import AgentWallet
    cols = {c.name for c in AgentWallet.__table__.columns}
    for required in {
        "id", "agent_id", "withdrawable", "total_earned",
        "total_withdrawn", "updated_at",
    }:
        assert required in cols, f"AgentWallet missing column {required}"


def test_rebind_request_has_required_columns():
    from models.agent import RebindRequest
    cols = {c.name for c in RebindRequest.__table__.columns}
    for required in {
        "id", "account_id", "from_agent_id", "to_agent_id",
        "status", "reviewer_id", "review_note",
        "created_at", "reviewed_at",
    }:
        assert required in cols, f"RebindRequest missing column {required}"


def test_withdrawal_request_has_required_columns():
    from models.agent import WithdrawalRequest
    cols = {c.name for c in WithdrawalRequest.__table__.columns}
    for required in {
        "id", "agent_id", "amount", "payout_method",
        "payout_payload", "status", "reviewer_id",
        "review_note", "created_at", "reviewed_at",
    }:
        assert required in cols, f"WithdrawalRequest missing column {required}"
```

**Step 2: 运行测试验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'models.agent'`

**Step 3: 写实现**

```python
# api/models/agent.py
"""SQLAlchemy models for the agent system.

See docs/plans/2026-04-30-agent-system-design.md §2 for the data model.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import TypeBase
from models.types import StringUUID


class AgentStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class AgentLevel(enum.StrEnum):
    NATIONAL = "national"
    PROVINCE = "province"
    CITY = "city"


class RebindStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class WithdrawalStatus(enum.StrEnum):
    PENDING = "pending"
    PAID = "paid"
    REJECTED = "rejected"


class PayoutMethod(enum.StrEnum):
    ALIPAY = "alipay"
    WECHAT = "wechat"
    BANK = "bank"


class Agent(TypeBase):
    """Authorized referral agent. One per account, opened by sysadmin."""

    __tablename__ = "agents"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="agent_pkey"),
        sa.Index("agent_account_id_idx", "account_id", unique=True),
        sa.Index("agent_status_idx", "status"),
        sa.Index("agent_expires_at_idx", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default=AgentStatus.ACTIVE.value,
        default=AgentStatus.ACTIVE.value,
    )
    rebate_rate: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(precision=5, scale=4), nullable=True, default=None,
    )
    level: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    region_province: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    region_city: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    signed_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True, default=None)
    expires_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True, default=None)
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
        onupdate=func.current_timestamp(),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "status": self.status,
            "rebate_rate": str(self.rebate_rate) if self.rebate_rate is not None else None,
            "level": self.level,
            "region_province": self.region_province,
            "region_city": self.region_city,
            "contact_phone": self.contact_phone,
            "notes": self.notes,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AgentWallet(TypeBase):
    """1:1 wallet per agent. All earnings + withdrawals flow through here."""

    __tablename__ = "agent_wallets"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="agent_wallet_pkey"),
        sa.Index("agent_wallet_agent_id_idx", "agent_id", unique=True),
        sa.CheckConstraint("withdrawable >= 0", name="agent_wallet_withdrawable_nonneg"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    withdrawable: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0),
    )
    total_earned: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0),
    )
    total_withdrawn: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
        onupdate=func.current_timestamp(),
    )


class RebindRequest(TypeBase):
    """Customer-initiated rebind to a different agent. Sysadmin-reviewed."""

    __tablename__ = "rebind_requests"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="rebind_request_pkey"),
        sa.Index("rebind_request_account_id_idx", "account_id"),
        sa.Index(
            "rebind_request_pending_unique_idx",
            "account_id",
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    from_agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    to_agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default=RebindStatus.PENDING.value,
        default=RebindStatus.PENDING.value,
    )
    reviewer_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class WithdrawalRequest(TypeBase):
    """Agent-initiated withdrawal. Sysadmin marks paid after offline transfer."""

    __tablename__ = "withdrawal_requests"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="withdrawal_request_pkey"),
        sa.Index("withdrawal_request_agent_id_idx", "agent_id"),
        sa.Index(
            "withdrawal_request_pending_unique_idx",
            "agent_id",
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), nullable=False,
    )
    payout_method: Mapped[str] = mapped_column(String(16), nullable=False)
    payout_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default=WithdrawalStatus.PENDING.value,
        default=WithdrawalStatus.PENDING.value,
    )
    reviewer_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
```

**Step 4: 运行测试验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py -v
```

Expected: `4 passed`

**Step 5: Commit**

```bash
git add api/models/agent.py api/tests/unit_tests/models/test_agent_models.py
git commit -m "feat(agent): add Agent / AgentWallet / RebindRequest / WithdrawalRequest models"
```

---

## Task 0.2:在 AccountInvitation 加 agent_id 字段并放宽 invite_code 索引

**Files:**
- Modify: `api/models/creator.py:288-326` (AccountInvitation class)
- Modify: `api/tests/unit_tests/models/test_agent_models.py` (加新测试)

**背景:** 设计文档 §2.2 说 `account_invitations.agent_id NOT NULL`,且原 unique 索引 `account_invitation_code_idx` 因为本期 code 多次复用要改成非唯一(同一 code 会有多个 invitee 行)。

**Step 1: 写失败测试**

```python
# 加到 api/tests/unit_tests/models/test_agent_models.py 末尾
def test_account_invitation_has_agent_id_column():
    from models.creator import AccountInvitation
    cols = {c.name for c in AccountInvitation.__table__.columns}
    assert "agent_id" in cols, "AccountInvitation must reference agent"


def test_account_invitation_invite_code_no_longer_unique():
    """Code is reusable now — same code can have multiple invitee rows."""
    from models.creator import AccountInvitation
    for idx in AccountInvitation.__table__.indexes:
        if idx.name == "account_invitation_code_idx":
            assert not idx.unique, "code index must not be unique anymore"
            return
    assert False, "account_invitation_code_idx not found"
```

**Step 2: 运行测试验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py::test_account_invitation_has_agent_id_column -v
```

Expected: `AssertionError: AccountInvitation must reference agent`

**Step 3: 写实现 — 修改 `api/models/creator.py:288-326`**

在 AccountInvitation 类的 `__table_args__` 中把 `account_invitation_code_idx` 的 `unique=True` 删掉,在字段中加 `agent_id`:

```python
# 修改前(line ~298):
sa.Index("account_invitation_code_idx", "invite_code", unique=True),
# 修改后:
sa.Index("account_invitation_code_idx", "invite_code"),

# 在 invitee_account_id 后增加(line ~308):
agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
```

注意 `to_dict()` 也要加 `"agent_id": self.agent_id`。

**Step 4: 运行测试验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py -v
```

Expected: `6 passed`

**Step 5: Commit**

```bash
git add api/models/creator.py api/tests/unit_tests/models/test_agent_models.py
git commit -m "feat(agent): add agent_id to AccountInvitation, relax code uniqueness"
```

---

## Task 0.3:在 RebateRecord 加 agent_id 字段

**Files:**
- Modify: `api/models/creator.py:397-470` (RebateRecord class)
- Modify: `api/tests/unit_tests/models/test_agent_models.py`

**Step 1: 写失败测试**

```python
def test_rebate_record_has_agent_id_column():
    from models.creator import RebateRecord
    cols = {c.name for c in RebateRecord.__table__.columns}
    assert "agent_id" in cols, "RebateRecord must reference agent"
```

**Step 2: 运行测试验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py::test_rebate_record_has_agent_id_column -v
```

Expected: `AssertionError`

**Step 3: 写实现 — 在 RebateRecord 的 inviter_account_id 后(line ~420)加字段**

```python
agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
```

加索引到 `__table_args__`:

```python
sa.Index("rebate_record_agent_idx", "agent_id"),
```

`to_dict()` 加 `"agent_id": self.agent_id`。

**Step 4: 运行测试**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py -v
```

Expected: `7 passed`

**Step 5: Commit**

```bash
git add api/models/creator.py api/tests/unit_tests/models/test_agent_models.py
git commit -m "feat(agent): add agent_id to RebateRecord"
```

---

## Task 0.4:从 UserBalance 删除 rebate_pending 字段

**Files:**
- Modify: `api/models/creator.py:71-117` (UserBalance class)
- Modify: `api/tests/unit_tests/models/test_agent_models.py`

**Step 1: 写失败测试**

```python
def test_user_balance_no_longer_has_rebate_pending():
    from models.creator import UserBalance
    cols = {c.name for c in UserBalance.__table__.columns}
    assert "rebate_pending" not in cols, "rebate_pending should be removed"
```

**Step 2: 验证测试失败**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py::test_user_balance_no_longer_has_rebate_pending -v
```

Expected: `AssertionError: rebate_pending should be removed`

**Step 3: 写实现 — 在 `api/models/creator.py:71-117` 删除 `rebate_pending` 字段定义和注释**

删除 lines ~83-103 整段(包括 `# Frozen rebate income...` 开头的注释和 `rebate_pending: Mapped[...]` 字段定义)。同时简化 `is_sufficient` docstring(把 "Only ``balance`` counts — ``rebate_pending`` is frozen..." 部分改成 "Returns True if spendable balance > 0")。

**Step 4: 运行测试**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py -v
```

Expected: `8 passed`

注意:此时其他引用 `rebate_pending` 的代码(`rebate_settlement_task.py` / `rebate_unfreeze_task.py`)**会编译失败**——这是正常的,Phase 3 会改造它们。Phase 0 阶段只需保证 model 测试通过。

**Step 5: Commit**

```bash
git add api/models/creator.py api/tests/unit_tests/models/test_agent_models.py
git commit -m "feat(agent): remove rebate_pending from UserBalance (moved to AgentWallet)"
```

---

## Task 0.5:写 alembic 迁移文件

**Files:**
- Create: `api/migrations/versions/2026_04_30_1200-<HASH>_add_agent_system.py`

**Step 1: 生成迁移骨架**

```bash
uv run --project api flask db revision -m "add agent system"
```

这会在 `api/migrations/versions/` 生成形如 `<hash>_add_agent_system.py` 的空骨架。复制 hash 到下面 Step 2 的内容里。

**Step 2: 写迁移内容**

替换骨架文件内容为(注意 `down_revision` 保留 `flask db revision` 自动填的值,**不要手改**):

```python
"""add agent system

Phase 0 of the agent system rollout. Creates 4 new tables, adds agent_id
to existing invitation/rebate tables, and removes rebate_pending from
UserBalance. Historic invitation/rebate data is wiped (per design §6.1).

Revision ID: <KEEP_AUTO_HASH>
Revises: f8a1c2b3d4e5
Create Date: 2026-04-30 12:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '<KEEP_AUTO_HASH>'  # 由 flask db revision 自动填
down_revision = 'f8a1c2b3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create agents table
    op.create_table(
        'agents',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
        sa.Column('rebate_rate', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('level', sa.String(length=16), nullable=True),
        sa.Column('region_province', sa.String(length=32), nullable=True),
        sa.Column('region_city', sa.String(length=32), nullable=True),
        sa.Column('contact_phone', sa.String(length=32), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('signed_at', sa.Date(), nullable=True),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='agent_pkey'),
    )
    op.create_index('agent_account_id_idx', 'agents', ['account_id'], unique=True)
    op.create_index('agent_status_idx', 'agents', ['status'])
    op.create_index('agent_expires_at_idx', 'agents', ['expires_at'])

    # 2. Create agent_wallets table
    op.create_table(
        'agent_wallets',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('withdrawable', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
        sa.Column('total_earned', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
        sa.Column('total_withdrawn', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='agent_wallet_pkey'),
        sa.CheckConstraint('withdrawable >= 0', name='agent_wallet_withdrawable_nonneg'),
    )
    op.create_index('agent_wallet_agent_id_idx', 'agent_wallets', ['agent_id'], unique=True)

    # 3. Create rebind_requests table
    op.create_table(
        'rebind_requests',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('from_agent_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('to_agent_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('reviewer_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='rebind_request_pkey'),
    )
    op.create_index('rebind_request_account_id_idx', 'rebind_requests', ['account_id'])
    op.create_index(
        'rebind_request_pending_unique_idx', 'rebind_requests', ['account_id'],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )

    # 4. Create withdrawal_requests table
    op.create_table(
        'withdrawal_requests',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('amount', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('payout_method', sa.String(length=16), nullable=False),
        sa.Column('payout_payload', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('reviewer_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='withdrawal_request_pkey'),
    )
    op.create_index('withdrawal_request_agent_id_idx', 'withdrawal_requests', ['agent_id'])
    op.create_index(
        'withdrawal_request_pending_unique_idx', 'withdrawal_requests', ['agent_id'],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )

    # 5. Add agent_id columns to existing tables (nullable temporarily)
    op.add_column('account_invitations', sa.Column('agent_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('rebate_records', sa.Column('agent_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.create_index('rebate_record_agent_idx', 'rebate_records', ['agent_id'])

    # 6. WIPE historic data (per design §6.1 — historic referrals are obsolete)
    op.execute('TRUNCATE rebate_records CASCADE')
    op.execute('TRUNCATE account_invitations CASCADE')

    # 7. Now make agent_id NOT NULL
    op.alter_column('account_invitations', 'agent_id', nullable=False)
    op.alter_column('rebate_records', 'agent_id', nullable=False)

    # 8. Drop old unique constraint on account_invitations.invite_code
    #    (code is now reusable across multiple invitees — same code, multiple rows)
    op.drop_index('account_invitation_code_idx', table_name='account_invitations')
    op.create_index('account_invitation_code_idx', 'account_invitations', ['invite_code'])

    # 9. Drop rebate_pending from user_balances
    op.drop_column('user_balances', 'rebate_pending')


def downgrade():
    # Reverse order. NOTE: TRUNCATE'd data is NOT recoverable — back up before
    # rolling back this migration in production.
    op.add_column('user_balances', sa.Column(
        'rebate_pending', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False,
    ))
    op.drop_index('account_invitation_code_idx', table_name='account_invitations')
    op.create_index('account_invitation_code_idx', 'account_invitations', ['invite_code'], unique=True)
    op.drop_index('rebate_record_agent_idx', table_name='rebate_records')
    op.drop_column('rebate_records', 'agent_id')
    op.drop_column('account_invitations', 'agent_id')
    op.drop_table('withdrawal_requests')
    op.drop_table('rebind_requests')
    op.drop_table('agent_wallets')
    op.drop_table('agents')
```

**Step 3: 运行迁移并验证**

```bash
uv run --project api flask db upgrade
```

Expected:`Running upgrade f8a1c2b3d4e5 -> <hash>, add agent system`

**Step 4: 验证表结构**

```bash
uv run --project api python -c "
from app_factory import create_app
app = create_app()
with app.app_context():
    from extensions.ext_database import db
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    for t in ['agents', 'agent_wallets', 'rebind_requests', 'withdrawal_requests']:
        assert insp.has_table(t), f'missing table {t}'
        print(f'{t}: OK')
    cols = [c['name'] for c in insp.get_columns('user_balances')]
    assert 'rebate_pending' not in cols, 'rebate_pending should be dropped'
    print('user_balances no rebate_pending: OK')
"
```

Expected: 4 行 `OK` + `user_balances no rebate_pending: OK`

**Step 5: Commit**

```bash
git add api/migrations/versions/
git commit -m "feat(agent): alembic migration for agent system schema"
```

---

## Task 0.6:验证迁移可回滚

**Files:** 无新文件,只验证

**Step 1: downgrade**

```bash
uv run --project api flask db downgrade
```

Expected:`Running downgrade <hash> -> f8a1c2b3d4e5`

**Step 2: 验证回滚后表消失**

```bash
uv run --project api python -c "
from app_factory import create_app
app = create_app()
with app.app_context():
    from extensions.ext_database import db
    from sqlalchemy import inspect
    insp = inspect(db.engine)
    for t in ['agents', 'agent_wallets', 'rebind_requests', 'withdrawal_requests']:
        assert not insp.has_table(t), f'{t} should be dropped'
    cols = [c['name'] for c in insp.get_columns('user_balances')]
    assert 'rebate_pending' in cols, 'rebate_pending should be restored'
    print('Downgrade verified: OK')
"
```

Expected:`Downgrade verified: OK`

**Step 3: 重新 upgrade**

```bash
uv run --project api flask db upgrade
```

留作 Phase 1+ 的开发基础。

**Step 4: Commit**

无代码改动,本步无 commit(纯验证)。

---

## Task 0.7:Agent 模型领域异常

**Files:**
- Create: `api/services/errors/agent.py`
- Create: `api/tests/unit_tests/services/test_agent_errors.py`

**Step 1: 写失败测试**

```python
# api/tests/unit_tests/services/test_agent_errors.py
def test_agent_errors_are_importable_and_distinct():
    from services.errors.agent import (
        AgentNotFoundError,
        AgentSuspendedError,
        AgentAccountAlreadyExistsError,
        InvalidAgentInvitationCodeError,
        AlreadyBoundError,
        SelfBindError,
        RebindCooldownActiveError,
        DuplicatePendingRebindError,
        RebindRequestNotFoundError,
        WithdrawalAmountTooSmallError,
        InsufficientWithdrawableBalanceError,
        DuplicatePendingWithdrawalError,
        WithdrawalRequestNotFoundError,
    )
    # Each must inherit from a common AgentError base
    from services.errors.agent import AgentError
    assert issubclass(AgentNotFoundError, AgentError)
    assert issubclass(AgentSuspendedError, AgentError)
    # And from base.BaseServiceError
    from services.errors.base import BaseServiceError
    assert issubclass(AgentError, BaseServiceError)
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/test_agent_errors.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: 写实现**

```python
# api/services/errors/agent.py
"""Domain exceptions for the agent system."""
from services.errors.base import BaseServiceError


class AgentError(BaseServiceError):
    """Base class for agent-system domain errors."""


class AgentNotFoundError(AgentError):
    pass


class AgentSuspendedError(AgentError):
    pass


class AgentAccountAlreadyExistsError(AgentError):
    """The given account is already registered as an agent."""


class InvalidAgentInvitationCodeError(AgentError):
    pass


class AlreadyBoundError(AgentError):
    """Customer already bound to an agent — caller should switch to rebind flow."""


class SelfBindError(AgentError):
    """An agent cannot bind themselves as their own invitee."""


class RebindCooldownActiveError(AgentError):
    """90-day cooldown after a previous approved rebind has not elapsed."""


class DuplicatePendingRebindError(AgentError):
    pass


class RebindRequestNotFoundError(AgentError):
    pass


class WithdrawalAmountTooSmallError(AgentError):
    pass


class InsufficientWithdrawableBalanceError(AgentError):
    pass


class DuplicatePendingWithdrawalError(AgentError):
    pass


class WithdrawalRequestNotFoundError(AgentError):
    pass
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/test_agent_errors.py -v
```

Expected: `1 passed`

**Step 5: Commit**

```bash
git add api/services/errors/agent.py api/tests/unit_tests/services/test_agent_errors.py
git commit -m "feat(agent): domain exceptions for agent system"
```

---

## Task 0.8:`@agent_required` 装饰器骨架

**Files:**
- Modify: `api/controllers/console/wraps.py` (在文件末尾追加)
- Create: `api/tests/unit_tests/controllers/test_agent_required.py`

**Step 1: 写失败测试**

```python
# api/tests/unit_tests/controllers/test_agent_required.py
"""Verify @agent_required:
- raises Forbidden when user has no Agent record
- raises Forbidden when agent is suspended
- passes through when agent is active
"""
import pytest
from unittest.mock import MagicMock, patch
from werkzeug.exceptions import Forbidden


def _make_view():
    from controllers.console.wraps import agent_required

    @agent_required
    def view():
        return "OK"
    return view


def test_agent_required_blocks_non_agent():
    view = _make_view()
    with patch("controllers.console.wraps.current_user", MagicMock(id="acct1")):
        with patch("controllers.console.wraps.db") as mock_db:
            mock_db.session.scalar.return_value = None  # no agent
            with pytest.raises(Forbidden):
                view()


def test_agent_required_blocks_suspended_agent():
    from models.agent import Agent, AgentStatus
    view = _make_view()
    suspended = MagicMock(spec=Agent, status=AgentStatus.SUSPENDED.value)
    with patch("controllers.console.wraps.current_user", MagicMock(id="acct1")):
        with patch("controllers.console.wraps.db") as mock_db:
            mock_db.session.scalar.return_value = suspended
            with pytest.raises(Forbidden):
                view()


def test_agent_required_allows_active_agent():
    from models.agent import Agent, AgentStatus
    view = _make_view()
    active = MagicMock(spec=Agent, status=AgentStatus.ACTIVE.value)
    with patch("controllers.console.wraps.current_user", MagicMock(id="acct1")):
        with patch("controllers.console.wraps.db") as mock_db:
            mock_db.session.scalar.return_value = active
            assert view() == "OK"
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/controllers/test_agent_required.py -v
```

Expected: `ImportError: cannot import name 'agent_required'`

**Step 3: 写实现 — 在 `api/controllers/console/wraps.py` 末尾追加**

```python
def agent_required[**P, R](view: Callable[P, R]) -> Callable[P, R]:
    """Block requests from users who are not active agents.

    Looks up the Agent row tied to the current user's account_id and
    rejects any request where status != 'active'. Pairs with
    @login_required (must come AFTER it in decorator order).
    """
    @wraps(view)
    def decorated(*args: P.args, **kwargs: P.kwargs) -> R:
        from extensions.ext_database import db
        from flask_login import current_user
        from models.agent import Agent, AgentStatus
        from sqlalchemy import select
        from werkzeug.exceptions import Forbidden

        agent = db.session.scalar(
            select(Agent).where(Agent.account_id == current_user.id)
        )
        if agent is None or agent.status != AgentStatus.ACTIVE.value:
            raise Forbidden("Agent access required")
        # Stash for downstream handlers — they read the agent often.
        from flask import g
        g.current_agent = agent
        return view(*args, **kwargs)

    return decorated
```

**注意:** wraps.py 顶部已经 `from flask_login import current_user` 等导入,但 `Agent` 这种新依赖不要全局 import(避免循环依赖),延迟到函数内 import。

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/controllers/test_agent_required.py -v
```

Expected: `3 passed`

**Step 5: Commit**

```bash
git add api/controllers/console/wraps.py api/tests/unit_tests/controllers/test_agent_required.py
git commit -m "feat(agent): @agent_required decorator for console endpoints"
```

---

**Phase 0 完成检查:**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_agent_models.py api/tests/unit_tests/services/test_agent_errors.py api/tests/unit_tests/controllers/test_agent_required.py -v
```

Expected: 全部通过(共约 12 个测试用例)

---

# Phase 1:后端核心服务

每个 service 都按 model → service → 领域异常 的 dependency 顺序构建。所有 service 都在 `api/services/agent/` 包下。

## Task 1.1:`services/agent/` 包初始化

**Files:**
- Create: `api/services/agent/__init__.py`(空文件)
- Create: `api/tests/unit_tests/services/agent/__init__.py`(空文件)
- Create: `api/tests/unit_tests/services/agent/conftest.py`

**Step 1: 写 conftest 公共 fixture**

```python
# api/tests/unit_tests/services/agent/conftest.py
"""Shared fixtures for agent service tests."""
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest


@pytest.fixture
def admin_account_id():
    return str(uuid4())


@pytest.fixture
def agent_account_id():
    return str(uuid4())


@pytest.fixture
def invitee_account_id():
    return str(uuid4())


@pytest.fixture
def make_agent_kwargs(agent_account_id, admin_account_id):
    """Default kwargs for AgentService.create_agent."""
    return dict(
        account_id=agent_account_id,
        name="Test Agent",
        rebate_rate=Decimal("0.10"),
        level="province",
        region_province="广东",
        region_city=None,
        contact_phone="13800000000",
        notes=None,
        signed_at=date(2026, 4, 30),
        expires_at=date(2027, 4, 30),
        created_by=admin_account_id,
    )
```

**Step 2: 创建空 `__init__.py`**

```bash
touch api/services/agent/__init__.py
mkdir -p api/tests/unit_tests/services/agent
touch api/tests/unit_tests/services/agent/__init__.py
```

**Step 3: 验证 import 可用**

```bash
uv run --project api python -c "import services.agent; print('OK')"
```

Expected:`OK`

**Step 4: Commit**

```bash
git add api/services/agent/ api/tests/unit_tests/services/agent/
git commit -m "feat(agent): initialize services/agent package + test fixtures"
```

---

## Task 1.2:AgentService.create_agent — happy path

**Files:**
- Create: `api/services/agent/agent_service.py`
- Create: `api/tests/unit_tests/services/agent/test_agent_service.py`

**Step 1: 写失败测试**

```python
# api/tests/unit_tests/services/agent/test_agent_service.py
import pytest
from decimal import Decimal


def test_create_agent_inserts_agent_and_wallet(make_agent_kwargs, app_with_db):
    """Creating an agent must atomically create its wallet too."""
    from services.agent.agent_service import AgentService
    from models.agent import Agent, AgentWallet
    from extensions.ext_database import db
    from sqlalchemy import select

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        # Agent row exists
        assert agent.id
        assert agent.account_id == make_agent_kwargs["account_id"]
        assert agent.name == "Test Agent"
        assert agent.status == "active"

        # Wallet row exists with zeroes
        wallet = db.session.scalar(
            select(AgentWallet).where(AgentWallet.agent_id == agent.id)
        )
        assert wallet is not None
        assert wallet.withdrawable == Decimal("0")
        assert wallet.total_earned == Decimal("0")
        assert wallet.total_withdrawn == Decimal("0")
```

(`app_with_db` fixture 来自 `api/tests/unit_tests/conftest.py`,提供 Flask app + SQLite in-memory DB,设计文档 §3.1 conftest 信息)

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_service.py::test_create_agent_inserts_agent_and_wallet -v
```

Expected:`ModuleNotFoundError: services.agent.agent_service`

**Step 3: 写实现**

```python
# api/services/agent/agent_service.py
"""Agent CRUD — sysadmin-facing operations.

The service does NOT commit by default — callers compose the work into
their own transaction. This matches the project's invitation_service pattern.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from extensions.ext_database import db
from models.agent import Agent, AgentStatus, AgentWallet
from services.errors.agent import (
    AgentAccountAlreadyExistsError,
    AgentNotFoundError,
)


class AgentService:
    """Service for managing agent lifecycle (create / suspend / etc)."""

    @classmethod
    def create_agent(
        cls,
        *,
        account_id: str,
        name: str,
        created_by: str,
        rebate_rate: Optional[Decimal] = None,
        level: Optional[str] = None,
        region_province: Optional[str] = None,
        region_city: Optional[str] = None,
        contact_phone: Optional[str] = None,
        notes: Optional[str] = None,
        signed_at: Optional[date] = None,
        expires_at: Optional[date] = None,
    ) -> Agent:
        """Create a new Agent + AgentWallet atomically (caller commits)."""
        existing = db.session.scalar(select(Agent).where(Agent.account_id == account_id))
        if existing:
            raise AgentAccountAlreadyExistsError(
                f"account {account_id} is already an agent"
            )

        agent = Agent(
            account_id=account_id,
            name=name,
            rebate_rate=rebate_rate,
            level=level,
            region_province=region_province,
            region_city=region_city,
            contact_phone=contact_phone,
            notes=notes,
            signed_at=signed_at,
            expires_at=expires_at,
            created_by=created_by,
        )
        db.session.add(agent)
        db.session.flush()  # populate agent.id

        wallet = AgentWallet(agent_id=agent.id)
        db.session.add(wallet)
        return agent

    @classmethod
    def get_by_account_id(cls, account_id: str) -> Optional[Agent]:
        return db.session.scalar(select(Agent).where(Agent.account_id == account_id))

    @classmethod
    def get_by_id(cls, agent_id: str) -> Agent:
        agent = db.session.scalar(select(Agent).where(Agent.id == agent_id))
        if agent is None:
            raise AgentNotFoundError(f"agent {agent_id} not found")
        return agent
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_service.py -v
```

Expected:`1 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_service.py api/tests/unit_tests/services/agent/test_agent_service.py
git commit -m "feat(agent): AgentService.create_agent — happy path"
```

---

## Task 1.3:AgentService.create_agent — duplicate account rejected

**Files:**
- Modify: `api/tests/unit_tests/services/agent/test_agent_service.py`

**Step 1: 写失败测试**

```python
def test_create_agent_rejects_duplicate_account(make_agent_kwargs, app_with_db):
    from services.agent.agent_service import AgentService
    from services.errors.agent import AgentAccountAlreadyExistsError
    from extensions.ext_database import db

    with app_with_db.app_context():
        AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        with pytest.raises(AgentAccountAlreadyExistsError):
            AgentService.create_agent(**make_agent_kwargs)
```

**Step 2: 验证通过**(实现已在 Task 1.2 完成,这步是回归保护)

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_service.py::test_create_agent_rejects_duplicate_account -v
```

Expected:`1 passed`

**Step 3: Commit**

```bash
git add api/tests/unit_tests/services/agent/test_agent_service.py
git commit -m "test(agent): regression for duplicate agent account rejection"
```

---

## Task 1.4:AgentService.suspend_agent / update_agent

**Files:**
- Modify: `api/services/agent/agent_service.py`
- Modify: `api/tests/unit_tests/services/agent/test_agent_service.py`

**Step 1: 写失败测试**

```python
def test_suspend_agent_changes_status(make_agent_kwargs, app_with_db):
    from services.agent.agent_service import AgentService
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        AgentService.suspend_agent(agent.id)
        db.session.commit()

        refreshed = AgentService.get_by_id(agent.id)
        assert refreshed.status == "suspended"


def test_update_agent_changes_fields(make_agent_kwargs, app_with_db):
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        AgentService.update_agent(
            agent.id, rebate_rate=Decimal("0.15"), notes="bumped rate after Q2 review",
        )
        db.session.commit()

        refreshed = AgentService.get_by_id(agent.id)
        assert refreshed.rebate_rate == Decimal("0.15")
        assert refreshed.notes == "bumped rate after Q2 review"
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_service.py -v
```

Expected: 2 个新测试 fail (`AttributeError: type object 'AgentService' has no attribute 'suspend_agent'`)

**Step 3: 添加方法到 AgentService**

```python
@classmethod
def suspend_agent(cls, agent_id: str) -> Agent:
    """Mark agent as suspended. Their invite codes stop working immediately."""
    agent = cls.get_by_id(agent_id)
    agent.status = AgentStatus.SUSPENDED.value
    return agent


@classmethod
def update_agent(cls, agent_id: str, **fields) -> Agent:
    """Patch agent fields. Only whitelisted fields are accepted."""
    allowed = {
        "name", "rebate_rate", "level",
        "region_province", "region_city",
        "contact_phone", "notes", "signed_at", "expires_at",
    }
    agent = cls.get_by_id(agent_id)
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(f"field {k} not updatable")
        setattr(agent, k, v)
    return agent
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_service.py -v
```

Expected:`4 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_service.py api/tests/unit_tests/services/agent/test_agent_service.py
git commit -m "feat(agent): AgentService.suspend_agent + update_agent"
```

---

## Task 1.5:AgentInvitationService.generate_invitation_code

**Files:**
- Create: `api/services/agent/agent_invitation_service.py`
- Create: `api/tests/unit_tests/services/agent/test_agent_invitation_service.py`

**Step 1: 写失败测试**

```python
def test_generate_invitation_code_returns_unique_string(make_agent_kwargs, app_with_db):
    """Code is reusable, but newly-generated codes must each be unique
    across the table."""
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        code1 = AgentInvitationService.generate_invitation_code(agent.id)
        code2 = AgentInvitationService.generate_invitation_code(agent.id)
        assert code1 != code2
        assert len(code1) >= 8
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_invitation_service.py -v
```

Expected:`ModuleNotFoundError`

**Step 3: 写实现**

```python
# api/services/agent/agent_invitation_service.py
"""Agent invitation code generation + binding.

Codes are long-lived and reusable: the same code may be bound by multiple
invitees over time. The "binding" event is the AccountInvitation row, not
the code itself.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.agent import Agent, AgentStatus
from models.creator import AccountInvitation
from services.errors.agent import (
    AgentNotFoundError,
    AgentSuspendedError,
    AlreadyBoundError,
    InvalidAgentInvitationCodeError,
    SelfBindError,
)


class AgentInvitationService:
    """Generate codes (called by agent) and bind codes (called by invitee)."""

    CODE_LENGTH = 16  # urlsafe-base64 chars

    @classmethod
    def generate_invitation_code(cls, agent_id: str) -> str:
        """Mint a fresh reusable invitation code for the given agent.

        Stores a 'template row' in account_invitations with
        invitee_account_id=NULL — actual binding rows are inserted at bind time.
        """
        agent = db.session.scalar(select(Agent).where(Agent.id == agent_id))
        if agent is None:
            raise AgentNotFoundError(f"agent {agent_id} not found")

        # Loop until we land on a fresh code. Collision probability is
        # negligible (16 urlsafe chars ≈ 96 bits) but unique index will
        # catch any rare race.
        while True:
            code = secrets.token_urlsafe(cls.CODE_LENGTH)[: cls.CODE_LENGTH]
            existing = db.session.scalar(
                select(AccountInvitation).where(AccountInvitation.invite_code == code)
            )
            if existing is None:
                break

        # Anchor row: the code's "creation" is recorded as one row with no
        # invitee. Subsequent binds insert NEW rows with the same code +
        # actual invitee_account_id. The anchor lets us look up the agent
        # behind a code without needing a binding.
        anchor = AccountInvitation(
            invite_code=code,
            inviter_account_id=agent.account_id,
            invitee_account_id=None,
            agent_id=agent.id,
            status="pending",
        )
        db.session.add(anchor)
        return code
```

**注意:** `AccountInvitation.status='pending'` 在原系统里表示"未使用",这里复用语义——anchor row 永远 pending(因为 invitee_account_id 永远 NULL)。Bind 时会 INSERT 新行,status='used'。

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_invitation_service.py -v
```

Expected:`1 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_invitation_service.py api/tests/unit_tests/services/agent/test_agent_invitation_service.py
git commit -m "feat(agent): AgentInvitationService.generate_invitation_code"
```

---

## Task 1.6:AgentInvitationService.bind — happy path

**Files:**
- Modify: `api/services/agent/agent_invitation_service.py`
- Modify: `api/tests/unit_tests/services/agent/test_agent_invitation_service.py`

**Step 1: 写失败测试**

```python
def test_bind_inserts_binding_row(make_agent_kwargs, invitee_account_id, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from models.creator import AccountInvitation
    from extensions.ext_database import db
    from sqlalchemy import select, and_

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code = AgentInvitationService.generate_invitation_code(agent.id)
        db.session.commit()

        AgentInvitationService.bind(invite_code=code, invitee_account_id=invitee_account_id)
        db.session.commit()

        # New "used" row inserted, separate from the anchor
        rows = db.session.scalars(
            select(AccountInvitation).where(
                and_(
                    AccountInvitation.invite_code == code,
                    AccountInvitation.invitee_account_id == invitee_account_id,
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].status == "used"
        assert rows[0].agent_id == agent.id
        assert rows[0].inviter_account_id == agent.account_id
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_invitation_service.py -v
```

Expected:`AttributeError: ... has no attribute 'bind'`

**Step 3: 添加 bind 方法**

```python
@classmethod
def bind(cls, *, invite_code: str, invitee_account_id: str) -> Agent:
    """Bind invitee to the agent behind invite_code. Caller commits.

    Raises:
        InvalidAgentInvitationCodeError: code does not exist
        AgentSuspendedError: agent is suspended
        SelfBindError: invitee is the agent themselves
        AlreadyBoundError: invitee already bound to any agent
    """
    code = (invite_code or "").strip()
    if not code:
        raise InvalidAgentInvitationCodeError("empty code")

    # Find the anchor row (invitee_account_id IS NULL) for this code
    anchor = db.session.scalar(
        select(AccountInvitation).where(
            AccountInvitation.invite_code == code,
            AccountInvitation.invitee_account_id.is_(None),
        )
    )
    if anchor is None:
        raise InvalidAgentInvitationCodeError(f"code {code} not found")

    agent = db.session.scalar(select(Agent).where(Agent.id == anchor.agent_id))
    if agent is None:
        raise InvalidAgentInvitationCodeError("orphan invitation")
    if agent.status != AgentStatus.ACTIVE.value:
        raise AgentSuspendedError(f"agent {agent.id} is suspended")
    if agent.account_id == invitee_account_id:
        raise SelfBindError("cannot bind to self")

    # Reject if invitee already bound to anyone
    existing_binding = db.session.scalar(
        select(AccountInvitation).where(
            AccountInvitation.invitee_account_id == invitee_account_id,
            AccountInvitation.status == "used",
        )
    )
    if existing_binding:
        raise AlreadyBoundError(
            f"invitee {invitee_account_id} already bound to agent {existing_binding.agent_id}"
        )

    binding = AccountInvitation(
        invite_code=code,
        inviter_account_id=agent.account_id,
        invitee_account_id=invitee_account_id,
        agent_id=agent.id,
        status="used",
        used_at=naive_utc_now(),
    )
    db.session.add(binding)
    return agent
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_invitation_service.py -v
```

Expected:`2 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_invitation_service.py api/tests/unit_tests/services/agent/test_agent_invitation_service.py
git commit -m "feat(agent): AgentInvitationService.bind"
```

---

## Task 1.7:AgentInvitationService.bind — error branches

**Files:**
- Modify: `api/tests/unit_tests/services/agent/test_agent_invitation_service.py`

**Step 1: 添加 4 个测试用例**

```python
def test_bind_rejects_unknown_code(invitee_account_id, app_with_db):
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import InvalidAgentInvitationCodeError
    with app_with_db.app_context():
        with pytest.raises(InvalidAgentInvitationCodeError):
            AgentInvitationService.bind(invite_code="NOPE", invitee_account_id=invitee_account_id)


def test_bind_rejects_suspended_agent(make_agent_kwargs, invitee_account_id, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import AgentSuspendedError
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code = AgentInvitationService.generate_invitation_code(agent.id)
        db.session.commit()

        AgentService.suspend_agent(agent.id)
        db.session.commit()

        with pytest.raises(AgentSuspendedError):
            AgentInvitationService.bind(invite_code=code, invitee_account_id=invitee_account_id)


def test_bind_rejects_self_invite(make_agent_kwargs, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import SelfBindError
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code = AgentInvitationService.generate_invitation_code(agent.id)
        db.session.commit()

        with pytest.raises(SelfBindError):
            AgentInvitationService.bind(
                invite_code=code, invitee_account_id=agent.account_id,
            )


def test_bind_rejects_double_bind(make_agent_kwargs, invitee_account_id, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import AlreadyBoundError
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code = AgentInvitationService.generate_invitation_code(agent.id)
        db.session.commit()

        AgentInvitationService.bind(invite_code=code, invitee_account_id=invitee_account_id)
        db.session.commit()

        with pytest.raises(AlreadyBoundError):
            AgentInvitationService.bind(invite_code=code, invitee_account_id=invitee_account_id)
```

**Step 2: 验证通过**(实现已在 Task 1.6 完成)

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_invitation_service.py -v
```

Expected:`6 passed`

**Step 3: Commit**

```bash
git add api/tests/unit_tests/services/agent/test_agent_invitation_service.py
git commit -m "test(agent): bind error branches (unknown / suspended / self / double)"
```

---

## Task 1.8:RebindService.create_request — happy path

**Files:**
- Create: `api/services/agent/rebind_service.py`
- Create: `api/tests/unit_tests/services/agent/test_rebind_service.py`

**Step 1: 写失败测试**

```python
# api/tests/unit_tests/services/agent/test_rebind_service.py
import pytest


def test_create_request_inserts_pending(
    make_agent_kwargs, invitee_account_id, app_with_db,
):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.agent.rebind_service import RebindService
    from extensions.ext_database import db
    from uuid import uuid4
    from datetime import date

    with app_with_db.app_context():
        # Original agent X
        agent_x = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code_x = AgentInvitationService.generate_invitation_code(agent_x.id)
        db.session.commit()
        AgentInvitationService.bind(invite_code=code_x, invitee_account_id=invitee_account_id)
        db.session.commit()

        # Target agent Y (new account)
        kw_y = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Y"}
        agent_y = AgentService.create_agent(**kw_y)
        db.session.commit()

        req = RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id=agent_x.id,
            to_agent_id=agent_y.id,
        )
        db.session.commit()

        assert req.status == "pending"
        assert req.from_agent_id == agent_x.id
        assert req.to_agent_id == agent_y.id
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_rebind_service.py -v
```

Expected:`ModuleNotFoundError: services.agent.rebind_service`

**Step 3: 写实现**

```python
# api/services/agent/rebind_service.py
"""Rebind workflow: customer-initiated, sysadmin-approved.

Lifecycle: pending → approved/rejected
On approval: account_invitations.agent_id is updated to to_agent_id.
Historic rebate_records.agent_id is NEVER changed (pre-rebind earnings
stay with the original agent).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.agent import Agent, RebindRequest, RebindStatus
from models.creator import AccountInvitation
from services.errors.agent import (
    AgentNotFoundError,
    DuplicatePendingRebindError,
    RebindCooldownActiveError,
    RebindRequestNotFoundError,
)

COOLDOWN_DAYS = 90


class RebindService:
    """Manage rebind requests + sysadmin review."""

    @classmethod
    def create_request(
        cls, *, account_id: str, from_agent_id: str, to_agent_id: str,
    ) -> RebindRequest:
        # Validate both agents exist
        for aid in (from_agent_id, to_agent_id):
            if db.session.scalar(select(Agent).where(Agent.id == aid)) is None:
                raise AgentNotFoundError(f"agent {aid} not found")

        # No duplicate pending
        existing_pending = db.session.scalar(
            select(RebindRequest).where(
                and_(
                    RebindRequest.account_id == account_id,
                    RebindRequest.status == RebindStatus.PENDING.value,
                )
            )
        )
        if existing_pending:
            raise DuplicatePendingRebindError(
                f"account {account_id} already has a pending rebind"
            )

        # 90-day cooldown since last approved rebind
        last_approved = db.session.scalar(
            select(RebindRequest)
            .where(
                and_(
                    RebindRequest.account_id == account_id,
                    RebindRequest.status == RebindStatus.APPROVED.value,
                )
            )
            .order_by(RebindRequest.reviewed_at.desc())
        )
        if last_approved and last_approved.reviewed_at:
            elapsed = naive_utc_now() - last_approved.reviewed_at
            if elapsed < timedelta(days=COOLDOWN_DAYS):
                raise RebindCooldownActiveError(
                    f"cooldown active, {COOLDOWN_DAYS - elapsed.days} days remaining"
                )

        req = RebindRequest(
            account_id=account_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
        )
        db.session.add(req)
        db.session.flush()
        return req
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_rebind_service.py -v
```

Expected:`1 passed`

**Step 5: Commit**

```bash
git add api/services/agent/rebind_service.py api/tests/unit_tests/services/agent/test_rebind_service.py
git commit -m "feat(agent): RebindService.create_request — happy path"
```

---

## Task 1.9:RebindService.create_request — duplicate pending + cooldown

**Files:**
- Modify: `api/tests/unit_tests/services/agent/test_rebind_service.py`

**Step 1: 添加测试**

```python
def test_create_request_rejects_duplicate_pending(make_agent_kwargs, invitee_account_id, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.agent.rebind_service import RebindService
    from services.errors.agent import DuplicatePendingRebindError
    from extensions.ext_database import db
    from uuid import uuid4

    with app_with_db.app_context():
        agent_x = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code_x = AgentInvitationService.generate_invitation_code(agent_x.id)
        db.session.commit()
        AgentInvitationService.bind(invite_code=code_x, invitee_account_id=invitee_account_id)
        db.session.commit()

        kw_y = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Y"}
        agent_y = AgentService.create_agent(**kw_y)
        db.session.commit()

        RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id=agent_x.id, to_agent_id=agent_y.id,
        )
        db.session.commit()

        with pytest.raises(DuplicatePendingRebindError):
            RebindService.create_request(
                account_id=invitee_account_id,
                from_agent_id=agent_x.id, to_agent_id=agent_y.id,
            )


def test_cooldown_blocks_new_request_within_90_days(make_agent_kwargs, invitee_account_id, app_with_db):
    from datetime import datetime, timedelta
    from services.agent.agent_service import AgentService
    from services.agent.rebind_service import RebindService
    from services.errors.agent import RebindCooldownActiveError
    from models.agent import RebindRequest, RebindStatus
    from extensions.ext_database import db
    from uuid import uuid4

    with app_with_db.app_context():
        agent_x = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        kw_y = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Y"}
        agent_y = AgentService.create_agent(**kw_y)
        db.session.commit()

        # Manually insert a 50-days-old approved request — within cooldown
        past = datetime.utcnow() - timedelta(days=50)
        old_req = RebindRequest(
            account_id=invitee_account_id,
            from_agent_id=agent_x.id, to_agent_id=agent_y.id,
            status=RebindStatus.APPROVED.value,
            reviewed_at=past,
        )
        db.session.add(old_req)
        db.session.commit()

        kw_z = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Z"}
        agent_z = AgentService.create_agent(**kw_z)
        db.session.commit()

        with pytest.raises(RebindCooldownActiveError):
            RebindService.create_request(
                account_id=invitee_account_id,
                from_agent_id=agent_x.id, to_agent_id=agent_z.id,
            )


def test_cooldown_lifted_after_91_days(make_agent_kwargs, invitee_account_id, app_with_db):
    """At day 91 the cooldown is over and a new request is allowed."""
    from datetime import datetime, timedelta
    from services.agent.agent_service import AgentService
    from services.agent.rebind_service import RebindService
    from models.agent import RebindRequest, RebindStatus
    from extensions.ext_database import db
    from uuid import uuid4

    with app_with_db.app_context():
        agent_x = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        kw_y = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Y"}
        agent_y = AgentService.create_agent(**kw_y)
        db.session.commit()

        past = datetime.utcnow() - timedelta(days=91)
        db.session.add(RebindRequest(
            account_id=invitee_account_id,
            from_agent_id=agent_x.id, to_agent_id=agent_y.id,
            status=RebindStatus.APPROVED.value,
            reviewed_at=past,
        ))
        db.session.commit()

        kw_z = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Z"}
        agent_z = AgentService.create_agent(**kw_z)
        db.session.commit()

        # Should NOT raise
        req = RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id=agent_x.id, to_agent_id=agent_z.id,
        )
        db.session.commit()
        assert req.status == "pending"
```

**Step 2: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_rebind_service.py -v
```

Expected:`4 passed`

**Step 3: Commit**

```bash
git add api/tests/unit_tests/services/agent/test_rebind_service.py
git commit -m "test(agent): rebind request duplicate-pending + 90-day cooldown branches"
```

---

## Task 1.10:RebindService.approve / reject + 历史 rebate_records 不变(关键不变量)

**Files:**
- Modify: `api/services/agent/rebind_service.py`
- Modify: `api/tests/unit_tests/services/agent/test_rebind_service.py`

**Step 1: 写失败测试 — 关键测试**

```python
def test_approve_switches_invitation_but_keeps_historic_rebate(
    make_agent_kwargs, invitee_account_id, app_with_db,
):
    """The CORE invariant from design §5.4 — after approval:
    - account_invitations.agent_id flips to new agent
    - rebate_records.agent_id stays at original agent
    """
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.agent.rebind_service import RebindService
    from models.creator import AccountInvitation, RebateRecord
    from extensions.ext_database import db
    from sqlalchemy import select, and_
    from uuid import uuid4

    with app_with_db.app_context():
        agent_x = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code_x = AgentInvitationService.generate_invitation_code(agent_x.id)
        db.session.commit()
        AgentInvitationService.bind(invite_code=code_x, invitee_account_id=invitee_account_id)
        db.session.commit()

        # Pre-existing historic rebate record under agent_x
        historic = RebateRecord(
            inviter_account_id=agent_x.account_id,
            invitee_account_id=invitee_account_id,
            agent_id=agent_x.id,
            settlement_date="2026-04-15",
            consumption_amount=Decimal("100"),
            cost_amount=Decimal("0"),
            rebate_amount=Decimal("10"),
            rebate_rate=Decimal("0.10"),
            cost_rate=Decimal("0"),
            status="settled",
        )
        db.session.add(historic)
        db.session.commit()

        kw_y = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Y"}
        agent_y = AgentService.create_agent(**kw_y)
        db.session.commit()

        req = RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id=agent_x.id, to_agent_id=agent_y.id,
        )
        db.session.commit()

        admin_id = str(uuid4())
        RebindService.approve(req.id, reviewer_id=admin_id, note="ok")
        db.session.commit()

        # Binding row now points to agent_y
        binding = db.session.scalar(
            select(AccountInvitation).where(
                AccountInvitation.invitee_account_id == invitee_account_id,
                AccountInvitation.status == "used",
            )
        )
        assert binding.agent_id == agent_y.id

        # Historic rebate record STILL points to agent_x — invariant intact
        rec = db.session.scalar(select(RebateRecord).where(RebateRecord.id == historic.id))
        assert rec.agent_id == agent_x.id


def test_reject_marks_request_without_changing_binding(
    make_agent_kwargs, invitee_account_id, app_with_db,
):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.agent.rebind_service import RebindService
    from models.creator import AccountInvitation
    from extensions.ext_database import db
    from sqlalchemy import select
    from uuid import uuid4

    with app_with_db.app_context():
        agent_x = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code_x = AgentInvitationService.generate_invitation_code(agent_x.id)
        db.session.commit()
        AgentInvitationService.bind(invite_code=code_x, invitee_account_id=invitee_account_id)
        db.session.commit()

        kw_y = {**make_agent_kwargs, "account_id": str(uuid4()), "name": "Y"}
        agent_y = AgentService.create_agent(**kw_y)
        db.session.commit()

        req = RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id=agent_x.id, to_agent_id=agent_y.id,
        )
        db.session.commit()

        RebindService.reject(req.id, reviewer_id=str(uuid4()), note="not allowed")
        db.session.commit()

        # Binding still points to agent_x
        binding = db.session.scalar(
            select(AccountInvitation).where(
                AccountInvitation.invitee_account_id == invitee_account_id,
                AccountInvitation.status == "used",
            )
        )
        assert binding.agent_id == agent_x.id
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_rebind_service.py -v
```

Expected: 2 个新测试 fail (`AttributeError: ... 'approve'`)

**Step 3: 添加 approve/reject**

```python
@classmethod
def approve(cls, request_id: str, *, reviewer_id: str, note: Optional[str] = None) -> RebindRequest:
    """Approve rebind. Flips account_invitations.agent_id but does NOT touch rebate_records."""
    req = db.session.scalar(select(RebindRequest).where(RebindRequest.id == request_id))
    if req is None:
        raise RebindRequestNotFoundError(f"rebind {request_id} not found")
    if req.status != RebindStatus.PENDING.value:
        raise RebindRequestNotFoundError(f"rebind {request_id} not pending")

    # Flip the binding
    binding = db.session.scalar(
        select(AccountInvitation).where(
            and_(
                AccountInvitation.invitee_account_id == req.account_id,
                AccountInvitation.status == "used",
            )
        )
    )
    if binding is None:
        raise RebindRequestNotFoundError("invitee has no active binding")
    binding.agent_id = req.to_agent_id
    binding.inviter_account_id = (
        db.session.scalar(select(Agent).where(Agent.id == req.to_agent_id)).account_id
    )

    req.status = RebindStatus.APPROVED.value
    req.reviewer_id = reviewer_id
    req.review_note = note
    req.reviewed_at = naive_utc_now()
    return req


@classmethod
def reject(cls, request_id: str, *, reviewer_id: str, note: Optional[str] = None) -> RebindRequest:
    req = db.session.scalar(select(RebindRequest).where(RebindRequest.id == request_id))
    if req is None or req.status != RebindStatus.PENDING.value:
        raise RebindRequestNotFoundError(f"rebind {request_id} not pending")
    req.status = RebindStatus.REJECTED.value
    req.reviewer_id = reviewer_id
    req.review_note = note
    req.reviewed_at = naive_utc_now()
    return req
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_rebind_service.py -v
```

Expected:`6 passed`

**Step 5: Commit**

```bash
git add api/services/agent/rebind_service.py api/tests/unit_tests/services/agent/test_rebind_service.py
git commit -m "feat(agent): RebindService.approve + reject (preserves historic rebate_records.agent_id)"
```

---

## Task 1.11:WithdrawalService.create_request — happy path + amount/balance 校验

**Files:**
- Create: `api/services/agent/withdrawal_service.py`
- Create: `api/tests/unit_tests/services/agent/test_withdrawal_service.py`

**Step 1: 写失败测试**

```python
# api/tests/unit_tests/services/agent/test_withdrawal_service.py
import pytest
from decimal import Decimal


def test_create_request_with_sufficient_balance(make_agent_kwargs, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.withdrawal_service import WithdrawalService
    from models.agent import AgentWallet
    from extensions.ext_database import db
    from sqlalchemy import select

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        # Topup wallet for testing
        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        wallet.withdrawable = Decimal("500")
        db.session.commit()

        req = WithdrawalService.create_request(
            agent_id=agent.id,
            amount=Decimal("200"),
            payout_method="alipay",
            payout_payload={"account": "user@alipay.com", "name": "张三"},
        )
        db.session.commit()
        assert req.status == "pending"
        assert req.amount == Decimal("200")
        # Withdrawable not yet decremented (only on mark_paid)
        wallet2 = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        assert wallet2.withdrawable == Decimal("500")


def test_create_request_rejects_under_minimum(make_agent_kwargs, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.withdrawal_service import WithdrawalService
    from services.errors.agent import WithdrawalAmountTooSmallError
    from models.agent import AgentWallet
    from extensions.ext_database import db
    from sqlalchemy import select

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        wallet.withdrawable = Decimal("500")
        db.session.commit()

        with pytest.raises(WithdrawalAmountTooSmallError):
            WithdrawalService.create_request(
                agent_id=agent.id,
                amount=Decimal("99.99"),
                payout_method="alipay",
                payout_payload={"account": "x", "name": "y"},
            )


def test_create_request_rejects_overdraft(make_agent_kwargs, app_with_db):
    from services.agent.agent_service import AgentService
    from services.agent.withdrawal_service import WithdrawalService
    from services.errors.agent import InsufficientWithdrawableBalanceError
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        # Wallet starts at 0
        with pytest.raises(InsufficientWithdrawableBalanceError):
            WithdrawalService.create_request(
                agent_id=agent.id,
                amount=Decimal("200"),
                payout_method="alipay",
                payout_payload={"account": "x", "name": "y"},
            )
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_withdrawal_service.py -v
```

Expected:`ModuleNotFoundError`

**Step 3: 写实现**

```python
# api/services/agent/withdrawal_service.py
"""Withdrawal request creation + sysadmin payout."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.agent import (
    AgentWallet,
    PayoutMethod,
    WithdrawalRequest,
    WithdrawalStatus,
)
from services.errors.agent import (
    DuplicatePendingWithdrawalError,
    InsufficientWithdrawableBalanceError,
    WithdrawalAmountTooSmallError,
    WithdrawalRequestNotFoundError,
)

MIN_WITHDRAWAL = Decimal("100")


class WithdrawalService:
    """Agent-initiated withdrawals + sysadmin payouts."""

    @classmethod
    def create_request(
        cls, *,
        agent_id: str,
        amount: Decimal,
        payout_method: str,
        payout_payload: dict,
    ) -> WithdrawalRequest:
        if amount < MIN_WITHDRAWAL:
            raise WithdrawalAmountTooSmallError(f"min withdrawal is {MIN_WITHDRAWAL}")

        if payout_method not in {m.value for m in PayoutMethod}:
            raise ValueError(f"unknown payout method {payout_method}")

        # No duplicate pending
        existing = db.session.scalar(
            select(WithdrawalRequest).where(
                and_(
                    WithdrawalRequest.agent_id == agent_id,
                    WithdrawalRequest.status == WithdrawalStatus.PENDING.value,
                )
            )
        )
        if existing:
            raise DuplicatePendingWithdrawalError(
                f"agent {agent_id} already has a pending withdrawal"
            )

        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent_id))
        if wallet is None or wallet.withdrawable < amount:
            raise InsufficientWithdrawableBalanceError(
                f"available {wallet.withdrawable if wallet else 0} < requested {amount}"
            )

        req = WithdrawalRequest(
            agent_id=agent_id,
            amount=amount,
            payout_method=payout_method,
            payout_payload=payout_payload,
        )
        db.session.add(req)
        db.session.flush()
        return req
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_withdrawal_service.py -v
```

Expected:`3 passed`

**Step 5: Commit**

```bash
git add api/services/agent/withdrawal_service.py api/tests/unit_tests/services/agent/test_withdrawal_service.py
git commit -m "feat(agent): WithdrawalService.create_request + amount/balance guards"
```

---

## Task 1.12:WithdrawalService.mark_paid + reject(原子事务)

**Files:**
- Modify: `api/services/agent/withdrawal_service.py`
- Modify: `api/tests/unit_tests/services/agent/test_withdrawal_service.py`

**Step 1: 写失败测试**

```python
def test_mark_paid_atomically_decrements_wallet(make_agent_kwargs, app_with_db):
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from services.agent.withdrawal_service import WithdrawalService
    from models.agent import AgentWallet
    from extensions.ext_database import db
    from sqlalchemy import select
    from uuid import uuid4

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        wallet.withdrawable = Decimal("500")
        db.session.commit()

        req = WithdrawalService.create_request(
            agent_id=agent.id, amount=Decimal("200"),
            payout_method="alipay",
            payout_payload={"account": "x", "name": "y"},
        )
        db.session.commit()

        WithdrawalService.mark_paid(
            req.id, reviewer_id=str(uuid4()), transaction_id="TX12345",
        )
        db.session.commit()

        wallet2 = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        assert wallet2.withdrawable == Decimal("300")
        assert wallet2.total_withdrawn == Decimal("200")

        from models.agent import WithdrawalRequest
        req2 = db.session.scalar(select(WithdrawalRequest).where(WithdrawalRequest.id == req.id))
        assert req2.status == "paid"
        assert req2.review_note == "TX12345"


def test_reject_does_not_touch_wallet(make_agent_kwargs, app_with_db):
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from services.agent.withdrawal_service import WithdrawalService
    from models.agent import AgentWallet
    from extensions.ext_database import db
    from sqlalchemy import select
    from uuid import uuid4

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        wallet.withdrawable = Decimal("500")
        db.session.commit()

        req = WithdrawalService.create_request(
            agent_id=agent.id, amount=Decimal("200"),
            payout_method="alipay",
            payout_payload={"account": "x", "name": "y"},
        )
        db.session.commit()

        WithdrawalService.reject(req.id, reviewer_id=str(uuid4()), note="bad info")
        db.session.commit()

        wallet2 = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        assert wallet2.withdrawable == Decimal("500")  # unchanged
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_withdrawal_service.py -v
```

Expected: 2 个新 fail (`AttributeError: ... 'mark_paid'`)

**Step 3: 添加方法**

```python
@classmethod
def mark_paid(
    cls, request_id: str, *,
    reviewer_id: str, transaction_id: str,
) -> WithdrawalRequest:
    req = db.session.scalar(
        select(WithdrawalRequest).where(WithdrawalRequest.id == request_id)
    )
    if req is None or req.status != WithdrawalStatus.PENDING.value:
        raise WithdrawalRequestNotFoundError(f"withdrawal {request_id} not pending")

    wallet = db.session.scalar(
        select(AgentWallet).where(AgentWallet.agent_id == req.agent_id)
    )
    if wallet is None or wallet.withdrawable < req.amount:
        raise InsufficientWithdrawableBalanceError(
            "wallet balance changed since request created — abort payout"
        )

    wallet.withdrawable = wallet.withdrawable - req.amount
    wallet.total_withdrawn = wallet.total_withdrawn + req.amount

    req.status = WithdrawalStatus.PAID.value
    req.reviewer_id = reviewer_id
    req.review_note = transaction_id
    req.reviewed_at = naive_utc_now()
    return req


@classmethod
def reject(cls, request_id: str, *, reviewer_id: str, note: str) -> WithdrawalRequest:
    req = db.session.scalar(
        select(WithdrawalRequest).where(WithdrawalRequest.id == request_id)
    )
    if req is None or req.status != WithdrawalStatus.PENDING.value:
        raise WithdrawalRequestNotFoundError(f"withdrawal {request_id} not pending")
    req.status = WithdrawalStatus.REJECTED.value
    req.reviewer_id = reviewer_id
    req.review_note = note
    req.reviewed_at = naive_utc_now()
    return req
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_withdrawal_service.py -v
```

Expected:`5 passed`

**Step 5: Commit**

```bash
git add api/services/agent/withdrawal_service.py api/tests/unit_tests/services/agent/test_withdrawal_service.py
git commit -m "feat(agent): WithdrawalService.mark_paid + reject (atomic wallet update)"
```

---

## Task 1.13:AgentWalletService — credit_settled

**Files:**
- Create: `api/services/agent/agent_wallet_service.py`
- Create: `api/tests/unit_tests/services/agent/test_agent_wallet_service.py`

**Step 1: 写失败测试**

```python
def test_credit_settled_increments_withdrawable_and_total_earned(
    make_agent_kwargs, app_with_db,
):
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from services.agent.agent_wallet_service import AgentWalletService
    from models.agent import AgentWallet
    from extensions.ext_database import db
    from sqlalchemy import select

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        AgentWalletService.credit_settled(agent.id, Decimal("50.5"))
        db.session.commit()
        AgentWalletService.credit_settled(agent.id, Decimal("19.5"))
        db.session.commit()

        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        assert wallet.withdrawable == Decimal("70.0")
        assert wallet.total_earned == Decimal("70.0")
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_wallet_service.py -v
```

Expected:`ModuleNotFoundError`

**Step 3: 写实现**

```python
# api/services/agent/agent_wallet_service.py
"""Centralised wallet read/write — single source for all balance updates."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from extensions.ext_database import db
from models.agent import AgentWallet


class AgentWalletService:
    """Pure data-access wrapper. All wallet mutation goes through here so
    we have a single auditable place to add logging / metrics."""

    @classmethod
    def get_wallet(cls, agent_id: str) -> AgentWallet:
        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent_id))
        if wallet is None:
            raise ValueError(f"agent {agent_id} has no wallet")
        return wallet

    @classmethod
    def credit_settled(cls, agent_id: str, amount: Decimal) -> AgentWallet:
        """Add settled rebate to withdrawable + total_earned."""
        wallet = cls.get_wallet(agent_id)
        wallet.withdrawable = wallet.withdrawable + amount
        wallet.total_earned = wallet.total_earned + amount
        return wallet
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_wallet_service.py -v
```

Expected:`1 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_wallet_service.py api/tests/unit_tests/services/agent/test_agent_wallet_service.py
git commit -m "feat(agent): AgentWalletService.credit_settled"
```

---

## Task 1.14:AgentDashboardService — wallet summary

**Files:**
- Create: `api/services/agent/agent_dashboard_service.py`
- Create: `api/tests/unit_tests/services/agent/test_agent_dashboard_service.py`

**Step 1: 写失败测试**

```python
def test_wallet_summary_returns_4_metrics(make_agent_kwargs, app_with_db):
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from services.agent.agent_dashboard_service import AgentDashboardService
    from services.agent.agent_wallet_service import AgentWalletService
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        AgentWalletService.credit_settled(agent.id, Decimal("70"))
        db.session.commit()

        s = AgentDashboardService.wallet_summary(agent.id)
        assert s["withdrawable"] == Decimal("70")
        assert s["total_earned"] == Decimal("70")
        assert s["total_withdrawn"] == Decimal("0")
        # pending = sum of RebateRecord.status='pending' AND agent_id=agent
        assert s["pending"] == Decimal("0")  # no pending records
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_dashboard_service.py -v
```

Expected:`ModuleNotFoundError`

**Step 3: 写实现**

```python
# api/services/agent/agent_dashboard_service.py
"""Aggregate queries for the agent console homepage."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select

from extensions.ext_database import db
from models.agent import AgentWallet
from models.creator import (
    AccountInvitation,
    BillingRecord,
    BillingRecordType,
    RebateRecord,
    RebateRecordStatus,
)


class AgentDashboardService:
    @classmethod
    def wallet_summary(cls, agent_id: str) -> dict:
        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent_id))
        if wallet is None:
            raise ValueError(f"agent {agent_id} has no wallet")

        pending = db.session.scalar(
            select(func.coalesce(func.sum(RebateRecord.rebate_amount), 0)).where(
                and_(
                    RebateRecord.agent_id == agent_id,
                    RebateRecord.status == RebateRecordStatus.PENDING.value,
                )
            )
        ) or Decimal("0")

        return {
            "withdrawable": wallet.withdrawable,
            "total_earned": wallet.total_earned,
            "total_withdrawn": wallet.total_withdrawn,
            "pending": Decimal(str(pending)),
        }
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_dashboard_service.py -v
```

Expected:`1 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_dashboard_service.py api/tests/unit_tests/services/agent/test_agent_dashboard_service.py
git commit -m "feat(agent): AgentDashboardService.wallet_summary"
```

---

## Task 1.15:AgentDashboardService — daily consumption (7-day trend)

**Files:**
- Modify: `api/services/agent/agent_dashboard_service.py`
- Modify: `api/tests/unit_tests/services/agent/test_agent_dashboard_service.py`

**Step 1: 写失败测试**

```python
def test_daily_consumption_returns_per_day_totals(
    make_agent_kwargs, invitee_account_id, app_with_db,
):
    """Today + last 7 days, one row per day. Empty days return 0."""
    from datetime import date, datetime, timedelta
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.agent.agent_dashboard_service import AgentDashboardService
    from models.creator import BillingRecord, BillingRecordType
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code = AgentInvitationService.generate_invitation_code(agent.id)
        db.session.commit()
        AgentInvitationService.bind(invite_code=code, invitee_account_id=invitee_account_id)
        db.session.commit()

        # Insert a deduction yesterday
        yesterday = datetime.utcnow() - timedelta(days=1)
        # NOTE: BillingRecord schema may differ — check api/models/creator.py:118+
        # for actual fields. The test should use the real fields.
        # ... (full test harness)

        result = AgentDashboardService.daily_consumption(agent.id, days=7)
        # result is list[dict] of 7 entries (today + 6 prior), each
        # with date + consumption fields
        assert len(result) == 7
        # The yesterday entry should reflect the inserted deduction
        # (omitted detail — adapt to BillingRecord shape)
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_dashboard_service.py -v
```

Expected:`AttributeError: ... 'daily_consumption'`

**Step 3: 添加方法**

```python
@classmethod
def daily_consumption(cls, agent_id: str, *, days: int = 7) -> list[dict]:
    """Per-day total consumption by all invitees of this agent.

    Returns list ordered oldest → newest, length == `days`. Empty days
    return 0 (NOT omitted).
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    invitee_ids = db.session.scalars(
        select(AccountInvitation.invitee_account_id).where(
            and_(
                AccountInvitation.agent_id == agent_id,
                AccountInvitation.status == "used",
            )
        )
    ).all()

    if not invitee_ids:
        return [{"date": (start + timedelta(days=i)).isoformat(), "consumption": Decimal("0")} for i in range(days)]

    # Single GROUP BY query — N+1 protection
    rows = db.session.execute(
        select(
            func.date(BillingRecord.created_at).label("d"),
            func.sum(func.abs(BillingRecord.amount)).label("total"),
        ).where(
            and_(
                BillingRecord.account_id.in_(invitee_ids),
                BillingRecord.record_type == BillingRecordType.DEDUCTION,
                BillingRecord.created_at >= datetime(start.year, start.month, start.day),
            )
        ).group_by(func.date(BillingRecord.created_at))
    ).all()

    by_date = {row.d.isoformat() if hasattr(row.d, "isoformat") else str(row.d): Decimal(str(row.total)) for row in rows}
    return [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "consumption": by_date.get((start + timedelta(days=i)).isoformat(), Decimal("0")),
        }
        for i in range(days)
    ]
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_dashboard_service.py -v
```

Expected:`2 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_dashboard_service.py api/tests/unit_tests/services/agent/test_agent_dashboard_service.py
git commit -m "feat(agent): AgentDashboardService.daily_consumption (7-day trend)"
```

---

## Task 1.16:AgentDashboardService — invitees aggregation(下级聚合表)

**Files:**
- Modify: `api/services/agent/agent_dashboard_service.py`
- Modify: `api/tests/unit_tests/services/agent/test_agent_dashboard_service.py`

**Step 1: 写失败测试**

```python
def test_invitees_aggregation_returns_per_invitee_rows(
    make_agent_kwargs, invitee_account_id, app_with_db,
):
    from services.agent.agent_service import AgentService
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.agent.agent_dashboard_service import AgentDashboardService
    from extensions.ext_database import db

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()
        code = AgentInvitationService.generate_invitation_code(agent.id)
        db.session.commit()
        AgentInvitationService.bind(invite_code=code, invitee_account_id=invitee_account_id)
        db.session.commit()

        rows = AgentDashboardService.invitees(agent.id)
        assert len(rows) == 1
        r = rows[0]
        assert r["invitee_account_id"] == invitee_account_id
        assert "bound_at" in r
        assert "month_consumption" in r
        assert "total_rebate" in r
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_dashboard_service.py -v
```

Expected:`AttributeError: ... 'invitees'`

**Step 3: 添加方法**

```python
@classmethod
def invitees(cls, agent_id: str) -> list[dict]:
    """Per-invitee rollup row for the dashboard.

    One single query: bindings JOIN aggregated rebate_records (month) +
    aggregated rebate_records (lifetime). N+1 protection.
    """
    today = date.today()
    month_start = date(today.year, today.month, 1)

    bindings = db.session.execute(
        select(
            AccountInvitation.invitee_account_id,
            AccountInvitation.used_at,
        ).where(
            and_(
                AccountInvitation.agent_id == agent_id,
                AccountInvitation.status == "used",
            )
        )
    ).all()

    if not bindings:
        return []

    invitee_ids = [b.invitee_account_id for b in bindings]

    # Month consumption
    month_consumption = dict(
        db.session.execute(
            select(
                BillingRecord.account_id,
                func.sum(func.abs(BillingRecord.amount)),
            ).where(
                and_(
                    BillingRecord.account_id.in_(invitee_ids),
                    BillingRecord.record_type == BillingRecordType.DEDUCTION,
                    BillingRecord.created_at >= datetime(month_start.year, month_start.month, month_start.day),
                )
            ).group_by(BillingRecord.account_id)
        ).all()
    )

    # Lifetime rebate per invitee for this agent
    lifetime_rebate = dict(
        db.session.execute(
            select(
                RebateRecord.invitee_account_id,
                func.sum(RebateRecord.rebate_amount),
            ).where(RebateRecord.agent_id == agent_id)
            .group_by(RebateRecord.invitee_account_id)
        ).all()
    )

    return [
        {
            "invitee_account_id": b.invitee_account_id,
            "bound_at": b.used_at.isoformat() if b.used_at else None,
            "month_consumption": Decimal(str(month_consumption.get(b.invitee_account_id, 0))),
            "total_rebate": Decimal(str(lifetime_rebate.get(b.invitee_account_id, 0))),
        }
        for b in bindings
    ]
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/test_agent_dashboard_service.py -v
```

Expected:`3 passed`

**Step 5: Commit**

```bash
git add api/services/agent/agent_dashboard_service.py api/tests/unit_tests/services/agent/test_agent_dashboard_service.py
git commit -m "feat(agent): AgentDashboardService.invitees (per-invitee rollup, single query)"
```

---

## Task 1.17:Account model `is_agent` / `agent_status` 属性扩展

**Files:**
- Modify: `api/models/account.py` (在 Account class 末尾追加 properties)
- Create: `api/tests/unit_tests/models/test_account_agent_props.py`

**Step 1: 写失败测试**

```python
def test_account_is_agent_returns_true_for_active_agent(make_agent_kwargs, app_with_db):
    from services.agent.agent_service import AgentService
    from models.account import Account
    from extensions.ext_database import db
    from sqlalchemy import select

    with app_with_db.app_context():
        # Insert a real Account row matching agent_kwargs.account_id
        from uuid import uuid4
        acct = Account(id=make_agent_kwargs["account_id"], email=f"{uuid4()}@x.com", name="X")
        db.session.add(acct)
        db.session.commit()

        AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        a = db.session.scalar(select(Account).where(Account.id == acct.id))
        assert a.is_agent is True
        assert a.agent_status == "active"


def test_account_is_agent_returns_false_for_normal_user(app_with_db):
    from models.account import Account
    from extensions.ext_database import db
    from uuid import uuid4

    with app_with_db.app_context():
        acct = Account(id=str(uuid4()), email=f"{uuid4()}@x.com", name="X")
        db.session.add(acct)
        db.session.commit()
        assert acct.is_agent is False
        assert acct.agent_status is None
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_account_agent_props.py -v
```

Expected:`AttributeError: 'Account' object has no attribute 'is_agent'`

**Step 3: 在 `api/models/account.py` Account class 中加 hybrid_property**

```python
# 在 Account class 末尾追加
@property
def is_agent(self) -> bool:
    """True if this account has an active agent record."""
    from models.agent import Agent, AgentStatus
    from extensions.ext_database import db
    from sqlalchemy import select
    return db.session.scalar(
        select(Agent.id).where(
            Agent.account_id == self.id,
            Agent.status == AgentStatus.ACTIVE.value,
        )
    ) is not None


@property
def agent_status(self) -> str | None:
    """'active' / 'suspended' / None (not an agent)."""
    from models.agent import Agent
    from extensions.ext_database import db
    from sqlalchemy import select
    return db.session.scalar(
        select(Agent.status).where(Agent.account_id == self.id)
    )
```

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/models/test_account_agent_props.py -v
```

Expected:`2 passed`

**Step 5: Commit**

```bash
git add api/models/account.py api/tests/unit_tests/models/test_account_agent_props.py
git commit -m "feat(agent): Account.is_agent + agent_status properties"
```

---

## Task 1.18:Phase 1 完成 — 全套服务测试 sanity

**Files:** 无新文件

**Step 1: 跑全部 Phase 1 测试**

```bash
uv run --project api pytest api/tests/unit_tests/services/agent/ api/tests/unit_tests/models/test_agent_models.py api/tests/unit_tests/models/test_account_agent_props.py api/tests/unit_tests/services/test_agent_errors.py -v
```

Expected: 全部通过(预计约 25-30 个测试用例)

**Step 2: 跑 lint**

```bash
make lint
```

Expected: 无错误(允许 warning)

如有 lint 错误,修复后重提交。

**Step 3: Commit**(若有 lint 修复)

```bash
git add -A
git commit -m "chore(agent): fix lint after Phase 1"
```

---

# Phase 2:后端 API 端点

每个端点都按 contract → controller → 测试。所有代理控制台端点用 `@agent_required` 装饰器,所有后台超管端点用 `system_admin_required` 装饰器。

## Task 2.1:`POST /admin/agents` — 后台开通代理

**Files:**
- Create: `api/controllers/console/admin/__init__.py`(若不存在)
- Create: `api/controllers/console/admin/agent/__init__.py`
- Create: `api/controllers/console/admin/agent/agents.py`
- Create: `api/controllers/console/admin/agent/__init__.py` 导入 agents
- Create: `api/tests/unit_tests/controllers/console/admin/test_agents_admin.py`

**Step 1: 写失败测试**(用 Flask test client)

```python
# api/tests/unit_tests/controllers/console/admin/test_agents_admin.py
def test_post_admin_agents_creates_agent(client_with_admin, admin_account_id):
    """POST /admin/agents — sysadmin opens a new agent."""
    from uuid import uuid4
    target_account_id = str(uuid4())

    # Pre-insert the target account
    # ... (depending on conftest helpers)

    resp = client_with_admin.post("/console/api/admin/agents", json={
        "account_id": target_account_id,
        "name": "广东 Test Agent",
        "rebate_rate": "0.10",
        "level": "province",
        "region_province": "广东",
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["account_id"] == target_account_id
    assert data["status"] == "active"
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/controllers/console/admin/test_agents_admin.py -v
```

Expected:`404 Not Found` (route 不存在)

**Step 3: 写实现**

```python
# api/controllers/console/admin/agent/agents.py
"""Sysadmin endpoints for managing agents."""
from datetime import date
from decimal import Decimal
from typing import Optional

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import BadRequest

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
    system_admin_required,
)
from extensions.ext_database import db
from libs.login import login_required
from services.agent.agent_service import AgentService
from services.errors.agent import AgentAccountAlreadyExistsError


@console_ns.route("/admin/agents")
class AdminAgentsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def post(self):
        body = request.get_json() or {}
        try:
            agent = AgentService.create_agent(
                account_id=body["account_id"],
                name=body["name"],
                created_by=request.current_user.id if hasattr(request, "current_user") else None,
                rebate_rate=Decimal(body["rebate_rate"]) if body.get("rebate_rate") else None,
                level=body.get("level"),
                region_province=body.get("region_province"),
                region_city=body.get("region_city"),
                contact_phone=body.get("contact_phone"),
                notes=body.get("notes"),
                signed_at=date.fromisoformat(body["signed_at"]) if body.get("signed_at") else None,
                expires_at=date.fromisoformat(body["expires_at"]) if body.get("expires_at") else None,
            )
            db.session.commit()
            return agent.to_dict(), 201
        except AgentAccountAlreadyExistsError as e:
            db.session.rollback()
            raise BadRequest(str(e))
        except KeyError as e:
            raise BadRequest(f"missing field: {e}")
```

注意 `request.current_user.id`:实际上 `from flask_login import current_user` + `current_user.id` 才是项目惯例,改成那个。

```python
# 顶部导入修正:
from flask_login import current_user
# 然后:
created_by=current_user.id,
```

**Step 4: 注册路由**

确认 `api/controllers/console/admin/__init__.py`(可能已存在)中有 `from controllers.console.admin.agent import agents` 等。如不存在则创建空目录 + `__init__.py` 导入 agents 模块。

```bash
mkdir -p api/controllers/console/admin/agent
touch api/controllers/console/admin/__init__.py api/controllers/console/admin/agent/__init__.py
echo "from . import agents" > api/controllers/console/admin/agent/__init__.py
```

并确认 `api/controllers/console/__init__.py` 末尾导入 admin 模块(原项目可能未导入,如未导入则补一行 `from controllers.console.admin import agent  # noqa`)。

**Step 5: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/controllers/console/admin/test_agents_admin.py -v
```

Expected:`1 passed`

**Step 6: Commit**

```bash
git add api/controllers/console/admin/ api/tests/unit_tests/controllers/console/admin/
git commit -m "feat(agent): POST /admin/agents endpoint"
```

---

## Task 2.2 - 2.4:剩余后台超管端点的简化模板

接下来每个 admin 端点都按相同模板:写失败测试 → 实现 → 验证 → 提交。详细列表:

- **Task 2.2:** `GET /admin/agents` 列表 + 分页 + 筛选(status / level / region) + `GET /admin/agents/{id}` + `PATCH /admin/agents/{id}`
- **Task 2.3:** `GET /admin/rebind-requests?status=pending` + `POST /admin/rebind-requests/{id}/approve` + `POST /admin/rebind-requests/{id}/reject`
- **Task 2.4:** `GET /admin/withdrawals?status=pending` + `POST /admin/withdrawals/{id}/pay` + `POST /admin/withdrawals/{id}/reject`
- **Task 2.5:** `GET /admin/rebate-records`(只读总览,支持按 agent 筛选)+ `GET /admin/rebate-records/export` (CSV)
- **Task 2.6:** `GET /admin/agent-consumption`(消耗大盘,按 agent 维度聚合)

每个 endpoint 都按 Task 2.1 的同样 5 步走:写测试 → 失败 → 实现 → 通过 → 提交。每个 task 一个 commit,commit message 格式 `feat(agent): {VERB} {PATH} endpoint`。

为节省 plan 长度,只列每个 task 的关键测试用例和实现要点,完整代码省略——执行时参照 Task 2.1 的代码风格自行展开。

---

## Task 2.7:`GET /agent/dashboard` — 控制台首页

**Files:**
- Create: `api/controllers/console/agent/__init__.py`
- Create: `api/controllers/console/agent/dashboard.py`
- Create: `api/tests/unit_tests/controllers/console/agent/test_dashboard.py`

**Step 1: 写失败测试**

```python
def test_get_agent_dashboard_returns_summary_and_trend(client_with_agent, agent_id):
    resp = client_with_agent.get("/console/api/agent/dashboard")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "wallet" in data
    assert {"withdrawable", "total_earned", "total_withdrawn", "pending"} == set(data["wallet"].keys())
    assert "trend" in data
    assert len(data["trend"]) == 7  # 7-day trend
```

**Step 2-5: 同 Task 2.1 模板**

实现:

```python
# api/controllers/console/agent/dashboard.py
from flask import g
from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    agent_required,
    setup_required,
)
from libs.login import login_required
from services.agent.agent_dashboard_service import AgentDashboardService


@console_ns.route("/agent/dashboard")
class AgentDashboardApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @agent_required
    def get(self):
        agent = g.current_agent  # set by @agent_required
        return {
            "wallet": _decimal_to_str_dict(AgentDashboardService.wallet_summary(agent.id)),
            "trend": [
                {"date": r["date"], "consumption": str(r["consumption"])}
                for r in AgentDashboardService.daily_consumption(agent.id, days=7)
            ],
        }


def _decimal_to_str_dict(d: dict) -> dict:
    return {k: str(v) for k, v in d.items()}
```

Commit: `feat(agent): GET /agent/dashboard endpoint`

---

## Task 2.8 - 2.13:剩余代理控制台端点

- **Task 2.8:** `GET /agent/invitees` + `PATCH /agent/invitees/{invitee_account_id}/note`
- **Task 2.9:** `POST /agent/invitations`(生成新 code)+ `GET /agent/invitations`(已生成 code 列表)
- **Task 2.10:** `POST /agent/withdrawals`(创建提现申请)+ `GET /agent/withdrawals`(自己的申请历史)
- **Task 2.11:** `GET /agent/bind/preview?code=XXX`(无需登录,展示代理资料给客户看)
- **Task 2.12:** `POST /agent/bind/confirm`(客户登录后调,完成绑定)
- **Task 2.13:** `POST /agent/bind/rebind-request`(客户已绑定时,申请换绑)

注意 Task 2.11(`/agent/bind/preview`)是**唯一不需要登录**的端点(因为客户在注册前点链接就能看到代理是谁),需要在 wraps.py 上注意装饰器组合,**不加 @login_required**。

每个 task 同样 5 步,各自一个 commit。

---

## Task 2.14:Account profile 端点扩展 — 加 `is_agent` / `agent_status`

**Files:**
- Modify: `api/controllers/console/account/account.py`(找到现有 `/account/profile` GET 端点)
- Modify: 该端点的测试文件

**Step 1: 写失败测试 — 把 is_agent + agent_status 加到 profile 响应**

```python
def test_profile_includes_is_agent_for_agent_account(client_with_agent):
    resp = client_with_agent.get("/console/api/account/profile")
    data = resp.get_json()
    assert data.get("is_agent") is True
    assert data.get("agent_status") == "active"
```

**Step 2-5: 在现有 profile 响应字段中加这两个字段,从 current_user.is_agent / current_user.agent_status 读取**

具体实现:在现有 profile 序列化函数中追加:

```python
"is_agent": current_user.is_agent,
"agent_status": current_user.agent_status,
```

Commit: `feat(agent): expose is_agent + agent_status on /account/profile`

---

**Phase 2 完成检查:**

```bash
uv run --project api pytest api/tests/unit_tests/controllers/console/agent/ api/tests/unit_tests/controllers/console/admin/ -v
```

Expected: 全部通过(估计约 25 个测试)

---

# Phase 3:后端清理 + Celery 改造

## Task 3.1:删除旧 InvitationService + 旧 invitation/rebate controllers

**Files:**
- Delete: `api/services/invitation_service.py`
- Delete: `api/controllers/console/creator/invitation.py`
- Delete: `api/controllers/console/creator/rebate.py`
- Delete: `api/tests/unit_tests/services/test_invitation_service.py`(若存在)
- Delete: 相关 controller 测试文件

**Step 1: 验证当前测试套件状态(基线)**

```bash
uv run --project api pytest api/tests/unit_tests/ --collect-only -q 2>&1 | tail -10
```

记录下当前测试数。

**Step 2: 删除文件**

```bash
git rm api/services/invitation_service.py
git rm api/controllers/console/creator/invitation.py
git rm api/controllers/console/creator/rebate.py
# 同时删除相关测试
git rm api/tests/unit_tests/services/test_invitation_service.py 2>/dev/null || true
# 找到并删除 controller 测试
find api/tests -name "test_invitation*.py" -path "*/controllers/console/creator/*" -exec git rm {} \;
find api/tests -name "test_rebate*.py" -path "*/controllers/console/creator/*" -exec git rm {} \;
```

**Step 3: 在 `api/controllers/console/__init__.py` 或 `api/controllers/console/creator/__init__.py` 中删除对这些模块的 import**

```bash
grep -rn "from .invitation\|from .rebate\|from controllers.console.creator.invitation\|from controllers.console.creator.rebate\|InvitationService" api/ --include="*.py" | grep -v __pycache__
```

逐一删除找到的引用。

**Step 4: 验证**

```bash
uv run --project api pytest api/tests/unit_tests/ -q 2>&1 | tail -10
```

Expected: 测试不再 import 错误,只是数量减少。如有 import 错误,继续删除引用直到干净。

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor(agent): remove obsolete invitation_service + creator/{invitation,rebate} controllers"
```

---

## Task 3.2:从 email_register 删除 invite_code 入参与 InvitationService 调用

**Files:**
- Modify: `api/controllers/console/auth/email_register.py:32, 63, 188-210`
- Modify: 该文件的测试

**Step 1: 写失败测试**(`invite_code` 入参不再被接受)

```python
# 在 api/tests/unit_tests/controllers/console/auth/test_email_register.py 加测试
def test_email_register_ignores_invite_code_param(client):
    """invite_code is fully removed — sending it is silently ignored.
    Binding now happens via /agent/bind/confirm, not at registration time."""
    resp = client.post("/console/api/email-register", json={
        "email": "x@x.com", "code": "123456",
        "new_password": "Aa12345!", "password_confirm": "Aa12345!",
        "token": "VALID",
        "invite_code": "should_be_ignored",
    })
    # Should not error on the extra field, but invite_code should not be persisted
    # (verified via no AccountInvitation row created)
```

**Step 2: 验证此时测试可能 pass(invite_code 还在,但不报错)。** 我们要的是删除该字段后该测试仍然 pass。

**Step 3: 删除字段和调用** — 从 `email_register.py`:
- Line 32:删除 `from services.invitation_service import InvitationService`
- Line 63:删除 `invite_code: str | None = Field(default=None)`
- Line 188-210:删除整段 `if args.invite_code: ...` 块

**Step 4: 验证**

```bash
uv run --project api pytest api/tests/unit_tests/controllers/console/auth/test_email_register.py -v
```

Expected: 全部通过

**Step 5: Commit**

```bash
git add api/controllers/console/auth/email_register.py api/tests/unit_tests/controllers/console/auth/test_email_register.py
git commit -m "refactor(agent): drop invite_code from email-register (binding moved to /agent/bind)"
```

---

## Task 3.3:rebate_settlement_task 改造 — 加 agent JOIN 校验 + 写 agent_id

**Files:**
- Modify: `api/schedule/rebate_settlement_task.py`
- Modify: `api/tests/unit_tests/schedule/test_rebate_settlement_task.py`(若存在,否则创建)

**Step 1: 写失败测试 — 老的 inviter 不是 agent 时跳过**

```python
def test_settlement_skips_non_agent_inviter(make_agent_kwargs, app_with_db):
    """If account_invitations.inviter is not an active agent, no
    RebateRecord is written for that invitee."""
    from uuid import uuid4
    from datetime import datetime, timedelta
    from decimal import Decimal
    from models.creator import AccountInvitation, BillingRecord, BillingRecordType, RebateConfig, RebateRecord
    from extensions.ext_database import db
    from sqlalchemy import select
    from schedule.rebate_settlement_task import rebate_settlement_task

    with app_with_db.app_context():
        # No Agent created — inviter is just a normal account
        normal_inviter_id = str(uuid4())
        invitee_id = str(uuid4())

        # Insert a "used" binding pointing to a non-agent inviter
        binding = AccountInvitation(
            invite_code="OLD_CODE",
            inviter_account_id=normal_inviter_id,
            invitee_account_id=invitee_id,
            agent_id=str(uuid4()),  # fake agent_id (orphan)
            status="used",
        )
        db.session.add(binding)

        # Insert deduction yesterday
        yesterday = datetime.utcnow() - timedelta(days=1)
        db.session.add(BillingRecord(
            account_id=invitee_id, amount=Decimal("-100"),
            record_type=BillingRecordType.DEDUCTION,
            created_at=yesterday,
        ))

        # Enable rebate config
        cfg = db.session.scalar(select(RebateConfig)) or RebateConfig()
        cfg.is_enabled = True
        cfg.rebate_rate = Decimal("10")  # 10%
        db.session.add(cfg)
        db.session.commit()

        rebate_settlement_task()

        # Should NOT have created any RebateRecord (inviter is not an agent)
        recs = db.session.scalars(select(RebateRecord).where(RebateRecord.invitee_account_id == invitee_id)).all()
        assert len(recs) == 0
```

**Step 2: 验证 — 现在测试 fail(老代码会创建 record)**

```bash
uv run --project api pytest api/tests/unit_tests/schedule/test_rebate_settlement_task.py::test_settlement_skips_non_agent_inviter -v
```

**Step 3: 改造 task**

修改 `api/schedule/rebate_settlement_task.py:80-95`(`used_invitations` 查询那段),加 JOIN 过滤:

```python
from models.agent import Agent, AgentStatus

# 替代原来的:
# used_invitations = db.session.scalars(
#     select(AccountInvitation).where(AccountInvitation.status == "used")
# ).all()

# 改成:
used_invitations = db.session.scalars(
    select(AccountInvitation).join(
        Agent, Agent.id == AccountInvitation.agent_id
    ).where(
        AccountInvitation.status == "used",
        Agent.status == AgentStatus.ACTIVE.value,
    )
).all()
```

然后在 `RebateRecord(...)` 写入处(line 165 附近)加 `agent_id=inv.agent_id`(从 `invitee_to_inviter` 改造为 `invitee_to_inviter_and_agent` 字典)。

```python
# 旧 build map:
# invitee_to_inviter: dict[str, str] = {}
# for inv in used_invitations:
#     if inv.invitee_account_id:
#         invitee_to_inviter[inv.invitee_account_id] = inv.inviter_account_id

# 新版本:
invitee_to_inv: dict[str, AccountInvitation] = {}
for inv in used_invitations:
    if inv.invitee_account_id:
        invitee_to_inv[inv.invitee_account_id] = inv

# 在 RebateRecord 创建处:
inv = invitee_to_inv[invitee_account_id]
rebate_record = RebateRecord(
    inviter_account_id=inv.inviter_account_id,
    invitee_account_id=invitee_account_id,
    agent_id=inv.agent_id,  # NEW
    ...
)
```

并且 `UserBalance.rebate_pending` 的写入逻辑要**完全删除**(line ~185 `balance.rebate_pending = ...`)。settlement task 只创建 PENDING RebateRecord,不再触碰 wallet——unfreeze task 才搬到 wallet。

**Step 4: 验证通过**

```bash
uv run --project api pytest api/tests/unit_tests/schedule/test_rebate_settlement_task.py -v
```

Expected: 全部通过

**Step 5: Commit**

```bash
git add api/schedule/rebate_settlement_task.py api/tests/unit_tests/schedule/test_rebate_settlement_task.py
git commit -m "refactor(agent): rebate_settlement_task — agent JOIN guard + write agent_id, drop UserBalance touch"
```

---

## Task 3.4:rebate_unfreeze_task 改造 — 写 AgentWallet 而非 UserBalance

**Files:**
- Modify: `api/schedule/rebate_unfreeze_task.py`
- Modify: 测试

**Step 1: 写失败测试**

```python
def test_unfreeze_credits_agent_wallet(make_agent_kwargs, app_with_db):
    """After unfreeze, AgentWallet.withdrawable + total_earned reflect the rebate."""
    from datetime import datetime, timedelta
    from decimal import Decimal
    from services.agent.agent_service import AgentService
    from models.agent import AgentWallet
    from models.creator import RebateRecord, RebateConfig
    from extensions.ext_database import db
    from sqlalchemy import select
    from schedule.rebate_unfreeze_task import rebate_unfreeze_task
    from uuid import uuid4

    with app_with_db.app_context():
        agent = AgentService.create_agent(**make_agent_kwargs)
        db.session.commit()

        # Pending record older than freeze_days
        cfg = db.session.scalar(select(RebateConfig)) or RebateConfig()
        cfg.is_enabled = True
        cfg.freeze_days = 7
        db.session.add(cfg)

        old = datetime.utcnow() - timedelta(days=10)
        rec = RebateRecord(
            inviter_account_id=agent.account_id,
            invitee_account_id=str(uuid4()),
            agent_id=agent.id,
            settlement_date=(datetime.utcnow() - timedelta(days=10)).date().isoformat(),
            consumption_amount=Decimal("100"),
            cost_amount=Decimal("0"),
            rebate_amount=Decimal("10"),
            rebate_rate=Decimal("0.10"),
            cost_rate=Decimal("0"),
            status="pending",
            created_at=old,
        )
        db.session.add(rec)
        db.session.commit()

        rebate_unfreeze_task()

        wallet = db.session.scalar(select(AgentWallet).where(AgentWallet.agent_id == agent.id))
        assert wallet.withdrawable == Decimal("10")
        assert wallet.total_earned == Decimal("10")

        rec2 = db.session.scalar(select(RebateRecord).where(RebateRecord.id == rec.id))
        assert rec2.status == "settled"
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/schedule/test_rebate_unfreeze_task.py -v
```

**Step 3: 改造 task**

`api/schedule/rebate_unfreeze_task.py` 中所有 `UserBalance.rebate_pending` 操作替换为对 `AgentWallet` 的操作,通过 `AgentWalletService.credit_settled(record.agent_id, record.rebate_amount)` 实现。

具体:line ~110-130(`balance.rebate_pending = ...` 那段)替换为:

```python
from services.agent.agent_wallet_service import AgentWalletService
AgentWalletService.credit_settled(record.agent_id, record.rebate_amount)
```

完全删除 `UserBalance` 相关的查询/导入。

**Step 4-5:** 验证 + commit

```bash
git add api/schedule/rebate_unfreeze_task.py api/tests/unit_tests/schedule/test_rebate_unfreeze_task.py
git commit -m "refactor(agent): rebate_unfreeze_task — credit AgentWallet via AgentWalletService"
```

---

## Task 3.5:新增 agent_expiry_task

**Files:**
- Create: `api/schedule/agent_expiry_task.py`
- Create: `api/tests/unit_tests/schedule/test_agent_expiry_task.py`
- Modify: `api/extensions/ext_celery.py`(注册新 beat schedule)

**Step 1: 写失败测试**

```python
def test_expiry_task_suspends_expired_agents(make_agent_kwargs, app_with_db):
    from datetime import date, timedelta
    from services.agent.agent_service import AgentService
    from models.agent import Agent
    from extensions.ext_database import db
    from sqlalchemy import select
    from schedule.agent_expiry_task import agent_expiry_task

    with app_with_db.app_context():
        kw = {**make_agent_kwargs, "expires_at": date.today() - timedelta(days=1)}
        agent = AgentService.create_agent(**kw)
        db.session.commit()

        agent_expiry_task()

        refreshed = db.session.scalar(select(Agent).where(Agent.id == agent.id))
        assert refreshed.status == "suspended"


def test_expiry_task_leaves_active_agent_alone(make_agent_kwargs, app_with_db):
    from datetime import date, timedelta
    from services.agent.agent_service import AgentService
    from models.agent import Agent
    from extensions.ext_database import db
    from sqlalchemy import select
    from schedule.agent_expiry_task import agent_expiry_task

    with app_with_db.app_context():
        kw = {**make_agent_kwargs, "expires_at": date.today() + timedelta(days=30)}
        agent = AgentService.create_agent(**kw)
        db.session.commit()

        agent_expiry_task()

        refreshed = db.session.scalar(select(Agent).where(Agent.id == agent.id))
        assert refreshed.status == "active"
```

**Step 2: 验证失败**

```bash
uv run --project api pytest api/tests/unit_tests/schedule/test_agent_expiry_task.py -v
```

**Step 3: 写实现**

```python
# api/schedule/agent_expiry_task.py
"""Daily task: auto-suspend agents past their expires_at."""
import logging
from datetime import date

import click
from celery import shared_task
from sqlalchemy import and_, select

from extensions.ext_database import db
from models.agent import Agent, AgentStatus

logger = logging.getLogger(__name__)


@shared_task(queue="dataset")
def agent_expiry_task():
    today = date.today()
    expired = db.session.scalars(
        select(Agent).where(
            and_(
                Agent.expires_at != None,  # noqa: E711
                Agent.expires_at <= today,
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
    ).all()

    if not expired:
        click.echo("agent_expiry_task: no expired agents")
        return

    for agent in expired:
        agent.status = AgentStatus.SUSPENDED.value
        logger.info("agent_expiry_task: suspended agent=%s expires_at=%s", agent.id, agent.expires_at)

    db.session.commit()
    click.echo(f"agent_expiry_task: suspended {len(expired)} expired agents")
```

**Step 4: 注册 beat schedule** — 在 `api/extensions/ext_celery.py` 找到现有 beat schedule 字典(类似 `'rebate-settlement': { 'task': '...', 'schedule': ... }`),追加:

```python
'agent-expiry': {
    'task': 'schedule.agent_expiry_task.agent_expiry_task',
    'schedule': crontab(hour=0, minute=30),  # 每日凌晨 0:30
},
```

**Step 5: 验证 + commit**

```bash
uv run --project api pytest api/tests/unit_tests/schedule/test_agent_expiry_task.py -v
```

```bash
git add api/schedule/agent_expiry_task.py api/extensions/ext_celery.py api/tests/unit_tests/schedule/test_agent_expiry_task.py
git commit -m "feat(agent): agent_expiry_task auto-suspends agents past expires_at"
```

---

## Task 3.6:Phase 3 全套回归测试

```bash
uv run --project api pytest api/tests/unit_tests/ -q
```

Expected: 全部通过(预计约 30+ 个 agent-related 测试 + 现有测试不受 regress)

如有 fail,修复后 commit:`chore(agent): fix Phase 3 regression`

---

# Phase 4:前端 — 代理控制台

## Task 4.1:三个 contract 文件

**Files:**
- Create: `web/contract/console/agent.ts`
- Create: `web/contract/console/agent-bind.ts`
- Create: `web/contract/console/admin-agent.ts`

每个文件按 `web/contract/console/asset-library.ts` 风格(参见现有文件结构):
- 顶部 `import { type } from '@orpc/contract'` + `import { base } from '../base'`
- 导出 TypeScript types(AgentDashboardResponse、AgentInvitee、WithdrawalRequest 等)
- 每个 endpoint 一个 `export const xxxContract = base.route({ method, path }).input(...).output(...)`

**完整内容见执行时按 Phase 2 的 endpoint 定义对照写。**

每个 contract 文件一个 commit:
- `feat(agent/web): contract for agent console endpoints`
- `feat(agent/web): contract for customer bind endpoints`
- `feat(agent/web): contract for admin agent management endpoints`

---

## Task 4.2:agentLayout 路由组 + 守卫

**Files:**
- Create: `web/app/(agentLayout)/layout.tsx`
- Create: `web/app/(agentLayout)/agent/dashboard/page.tsx` (placeholder)
- Create: `web/__tests__/agent/layout.test.tsx`

**Step 1: 写失败测试**

```tsx
// web/__tests__/agent/layout.test.tsx
import { render, screen } from '@testing-library/react'
import AgentLayout from '@/app/(agentLayout)/layout'

describe('AgentLayout', () => {
  it('redirects non-agent users to /apps', async () => {
    // mock useProfile to return { is_agent: false }
    // ... render and assert redirect was called
  })

  it('redirects suspended agents with toast', async () => {
    // mock useProfile to return { is_agent: false, agent_status: 'suspended' }
    // ...
  })

  it('renders children for active agents', async () => {
    // mock useProfile to return { is_agent: true, agent_status: 'active' }
    // ...
  })
})
```

**Step 2: 验证失败 → Step 3: 实现 layout**

```tsx
// web/app/(agentLayout)/layout.tsx
'use client'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import Toast from '@/app/components/base/toast'
import { useProfile } from '@/service/use-account'  // 沿用现有 profile hook 路径

export default function AgentLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { data: profile, isLoading } = useProfile()

  useEffect(() => {
    if (isLoading) return
    if (!profile?.is_agent) {
      router.replace('/apps')
      return
    }
    if (profile.agent_status === 'suspended') {
      Toast.notify({ type: 'warning', message: '代理身份已暂停,请联系客服' })
      router.replace('/apps')
      return
    }
  }, [profile, isLoading, router])

  if (isLoading || !profile?.is_agent || profile.agent_status !== 'active')
    return null

  return (
    <div className="agent-layout-shell">
      <AgentTopNav />
      <main>{children}</main>
    </div>
  )
}

function AgentTopNav() {
  const router = useRouter()
  return (
    <nav className="agent-top-nav">
      <a href="/agent/dashboard">控制台</a>
      <a href="/agent/invitees">下级管理</a>
      <a href="/agent/invitation">邀请客户</a>
      <a href="/agent/withdrawal">提现</a>
      <button onClick={() => router.push('/apps')}>返回应用</button>
    </nav>
  )
}
```

**Step 4-5:** 验证 + commit:`feat(agent/web): agentLayout route group + auth guard`

---

## Task 4.3-4.6:四个控制台页

每个 page 按 TDD 顺序:测试组件渲染 → 实现页面 + 拆出 components/agent/* 组件 → 验证 → 提交。

- **Task 4.3:** `agent/dashboard/page.tsx` — 调 `agentDashboardContract`, 渲染 wallet 卡 + 7 日折线图(使用 recharts 或项目已用的 charting lib)
- **Task 4.4:** `agent/invitees/page.tsx` — 调 `agentInviteesContract`, 表格 + 关键字搜索 + 备注 inline 编辑 (PATCH)
- **Task 4.5:** `agent/invitation/page.tsx` — POST 生成 code, 显示链接 + QR(使用 `qrcode` npm 包) + 复制按钮
- **Task 4.6:** `agent/withdrawal/page.tsx` — 申请表单(支付方式 radio + 字段联动) + 申请历史列表

每个 task 一个 commit:`feat(agent/web): {页面名}`

---

## Task 4.7:BindConfirmDialog 组件

**Files:**
- Create: `web/app/components/agent/bind-confirm-dialog/index.tsx`
- Create: `web/__tests__/agent/bind-confirm-dialog.test.tsx`

**核心测试用例:**
1. 未绑定的客户:展示"确认绑定"按钮
2. 已绑定其他代理的客户:展示"申请换绑"按钮
3. 调 preview API 加载代理资料
4. 确认绑定 → 调 confirm API
5. 申请换绑 → 调 rebind-request API
6. 错误时显示 Toast

**实现要点:** 接收 `code` prop,组件挂载时自动调 `agentBindPreviewContract`,根据 preview 结果决定显示"绑定"还是"换绑";按钮 onClick 调对应 mutation。

Commit: `feat(agent/web): BindConfirmDialog`

---

## Task 4.8:i18n 文案

**Files:**
- Create: `web/i18n/zh-Hans/agent.json`
- Create: `web/i18n/en-US/agent.json`(机翻占位)
- Modify: `web/i18n/i18next-config.ts` 或对应 namespace 注册文件

i18n key 涵盖:控制台标题、菜单项、wallet 四指标、提现申请字段、绑定弹窗文案、错误消息等。

Commit: `feat(agent/web): i18n strings (zh-Hans + en-US)`

---

## Task 4.9-4.16:剩余前端 task

- **Task 4.9-4.10:** 上述每个页面的 RTL/Vitest 单元测试(分两次提交,UI 测 + 数据流测)
- **Task 4.11:** `web/service/use-agent.ts` — TanStack Query hook 封装(`useAgentDashboard`、`useAgentInvitees` 等)
- **Task 4.12-4.16:** 修复任何 lint/type-check 错误,跑 `pnpm type-check:tsgo` + `pnpm lint`

最后:`git push -u origin feat/agent-system`(若你想推到远端);否则保持本地分支。

---

# Phase 5:后台超管页 + 前端清理 + 登录 redirect

## Task 5.1-5.5:后台超管 5 页

按现有 admin 页面位置(查找 `web/app/(commonLayout)/` 下是否已有 admin 路由)创建:

- `agent-management/agents/page.tsx` — 代理列表 + 新建表单 + 编辑
- `agent-management/rebind-requests/page.tsx` — 待审批换绑列表 + 通过/拒绝
- `agent-management/withdrawals/page.tsx` — 待审批提现列表 + 标记已打款/拒绝
- `agent-management/rebate-records/page.tsx` — 只读返点总览,带 CSV 导出
- `agent-management/consumption/page.tsx` — 代理消耗大盘(只读)

每页一个 commit。

---

## Task 5.6-5.8:前端清理

- **Task 5.6:** 删除 `web/app/components/creator/settings/tabs/invitation-tab.tsx` + `rebate-tab.tsx` + `creator-settings-modal.tsx` 中的 invitation / rebate MENU_ITEMS 条目和路由分支
- **Task 5.7:** 删除 `web/service/use-common.ts` 中 `MailRegisterPayload.invite_code` 字段
- **Task 5.8:** 改造 `web/app/signup/page.tsx` + `web/app/signup/set-password/page.tsx` + `web/app/signin/page.tsx` —— `invite_code` query 改名为 `agent_code`,通过 sessionStorage 在登录/注册成功后触发 BindConfirmDialog

每个 task 一个 commit:`refactor(agent/web): remove legacy invitation/rebate UI`

---

## Task 5.9-5.12:登录 redirect 逻辑

- **Task 5.9:** 改 `web/app/signin/page.tsx` 登录成功回调 — 拿到 `is_agent + agent_status` 后决定跳 `/agent/dashboard` / `/apps` / 弹 toast
- **Task 5.10:** 普通界面右上角用户菜单加"代理商控制台"入口(只在 `is_agent=true` 时显示)
- **Task 5.11:** 跑 `pnpm type-check:tsgo` 全量类型检查
- **Task 5.12:** 跑 `pnpm lint --fix` 修复 ESLint 警告

每步一个 commit。

---

# Phase 6:E2E 测试

## Task 6.1-6.4:四个关键路径

- **Task 6.1:** 超管开通代理 → 代理登录 → 默认入控制台 → 生成邀请链接
- **Task 6.2:** 新用户访问邀请链接 → 注册 → 弹窗确认 → 控制台下级 +1
- **Task 6.3:** 已注册用户访问邀请链接 → 登录 → 弹窗确认
- **Task 6.4:** 代理申请提现 → 超管标记已打款 → 钱包扣款

每个 E2E 一个 spec 文件(`web/e2e/agent-{flow}.spec.ts`),一个 commit:`test(agent/e2e): {flow}`

---

## Task 6.5:数据迁移测试

**Files:**
- Create: `api/tests/unit_tests/migrations/test_agent_system_migration.py`

**Step 1: 写测试 — 用 SQLite in-memory 验证 upgrade + downgrade**

```python
def test_agent_system_migration_upgrade_creates_4_tables_and_drops_rebate_pending():
    """Confirm the alembic migration's upgrade leaves the schema as expected."""
    # ... full alembic-driven test using stamp/upgrade/downgrade
```

Commit: `test(agent): alembic migration regression test`

---

# 完成标准

- 所有 83 个 task 的测试都通过
- `make lint` 通过
- `pnpm type-check:tsgo` 通过
- `pnpm lint` 通过
- 4 个 E2E spec 在 Playwright 下通过
- 全部 commits push 到 `feat/agent-system` 分支

---

# 上线交付清单(交付前手工确认)

1. ✅ Alembic 迁移已在 staging DB 跑通
2. ✅ 超管账户能登录后台,代理管理页可见
3. ✅ 超管开通的测试代理登录后默认进入 `/agent/dashboard`
4. ✅ 测试代理生成邀请链接,新用户扫码注册后弹窗 + 二次确认
5. ✅ 测试代理消费触发后,在控制台可见 pending → settled → withdrawable 流转
6. ✅ 测试代理申请提现,超管在后台审批通过,钱包正确扣减
7. ✅ 旧的 invitation / rebate UI 入口完全消失
8. ✅ 普通用户访问 `/agent/*` 被 redirect

---

# 设计 → 实施落差(执行前确认)

实施过程中如果发现以下情况,**停下来跟产品确认**而不是自己拍板:

1. `BillingRecord` 实际 schema 与设计文档假设不符
2. `RebateConfig.rebate_rate` 单位是百分数(10 = 10%)还是小数(0.10 = 10%) — 在 settlement_task 里需要看清楚
3. 现有 `email_register` 流程对前端 `invite_code` 的依赖比预期深(目前看是 URL query → set-password 页 → API,理论上完全可删)
4. 前端图表库:`recharts` 是否已是项目依赖,若不是要在 plan 里追加 `pnpm add` task

---

# 附录:重要的设计 → 实施关键不变量

执行人若违背以下任一条,设计文档约束将被破坏:

1. **`rebate_records.agent_id` 写入时锁死,后续永不修改** — 换绑只动 `account_invitations.agent_id`
2. **`AgentWallet` 只通过 `AgentWalletService` 修改** — 其他 service 直接改 `withdrawable` 或 `total_earned` 是 bug
3. **`@agent_required` 必须查 `g.current_agent`** — 控制器函数不应自己再 `select(Agent)`
4. **rebate_settlement_task 的 JOIN agents 校验** — 这是"普通用户不再产生新返点"的硬执行点,不能放到上游业务
5. **每个代理同时只能一个 pending withdrawal / 客户同时只能一个 pending rebind** — partial unique index 强制
6. **`/agent/bind/preview` 是唯一不需要登录的代理端点** — 因为客户在注册前需要看到代理是谁
7. **代理永远看不到下级的对话内容、application、token 明细** — 隐私红线
