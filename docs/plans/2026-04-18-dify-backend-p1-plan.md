# Dify 后端 P1 实施计划：社交发布 - 账号管理

**日期**: 2026-04-18
**作者**: planner agent
**关联设计文档**: [2026-04-18-social-auto-upload-design.md](./2026-04-18-social-auto-upload-design.md)
**状态**: 待评审

---

## Overview

P1 阶段聚焦"账号管理"：在 Dify api 项目落地一张 `social_publish_account` 表 + 一组 REST 接口，
对接独立部署的 sau 服务完成抖音账号扫码授权与生命周期管理。**不涉及发布任务**（P2 范围）。
P1 完成后即可在前端做账号绑定/列表/删除，并通过隔离测试证明 A 用户不会看到 B 用户的账号。

## Requirements

- 仅支持 `platform="douyin"`（写死，平台扩展放 P4）
- 所有数据按 `tenant_id` 强隔离，控制层和服务层双重校验
- 扫码授权用 **session_id + 轮询**（不用 SSE），轮询数据存 Redis
- sau 服务通过共享密钥 `SAU_INTERNAL_TOKEN` 鉴权
- HTTPX 客户端实现连接池、超时、有限次重试，sau 不可达时给明确错误
- Feature flag `social_publish_enabled` 控制总开关
- 严格遵循 DDD 分层：controller → service → repository → model
- 单元测试 ≥80% 覆盖率，至少包含一个隔离测试（A 不能访问 B 的账号）

## Architecture Changes

| 文件路径 | 类型 | 说明 |
|---|---|---|
| `api/migrations/versions/2026_04_18_1000-<rev>_add_social_publish_account.py` | 新增 | Alembic 建表迁移 |
| `api/models/social_publish.py` | 新增 | `SocialPublishAccount` ORM model |
| `api/repositories/social_publish_account_repository.py` | 新增 | Repository Protocol（接口） |
| `api/repositories/sqlalchemy_social_publish_account_repository.py` | 新增 | SQLAlchemy 实现 |
| `api/repositories/factory.py` | 修改 | 增加 `create_social_publish_account_repository` |
| `api/services/sau_client.py` | 新增 | HTTPX 客户端，封装 sau API 调用 |
| `api/services/social_publish_service.py` | 新增 | 业务编排 + 隔离校验 |
| `api/services/errors/social_publish.py` | 新增 | 领域异常定义 |
| `api/controllers/console/social_publish/__init__.py` | 新增 | 包初始化 |
| `api/controllers/console/social_publish/accounts.py` | 新增 | 4 个 REST 接口 |
| `api/controllers/console/social_publish/error.py` | 新增 | HTTP 异常映射 |
| `api/controllers/console/__init__.py` | 修改 | 注册新 controller 模块 |
| `api/configs/feature/__init__.py` | 修改 | 增加 `SAU_BASE_URL` 等 env |
| `api/services/feature_service.py` | 修改 | 增加 `social_publish_enabled` 字段 |
| `api/.env.example` | 修改 | 增加 `SAU_*` 环境变量示例 |
| `api/tests/unit_tests/services/test_social_publish_service.py` | 新增 | service 层单测 |
| `api/tests/unit_tests/repositories/test_social_publish_account_repository.py` | 新增 | repository 层单测 |
| `api/tests/unit_tests/services/test_sau_client.py` | 新增 | sau client 单测（HTTPX mock） |
| `api/tests/unit_tests/controllers/console/social_publish/test_accounts.py` | 新增 | controller 层 + 隔离测试 |

---

## A. 数据库表结构 + Alembic 骨架

### A.1 表定义

```sql
CREATE TABLE social_publish_accounts (
  id              UUID         PRIMARY KEY,
  tenant_id       UUID         NOT NULL,
  platform        VARCHAR(16)  NOT NULL,                          -- douyin (P1)
  sau_account_id  VARCHAR(64)  NOT NULL,                          -- sau 内部 ID
  display_name    VARCHAR(64),                                     -- 抖音昵称
  avatar_url      TEXT,
  status          VARCHAR(16)  NOT NULL DEFAULT 'pending_auth',   -- active|expired|pending_auth
  last_check_at   TIMESTAMP,
  created_by      UUID         NOT NULL,                          -- account.id（审计）
  created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX  social_publish_account_tenant_platform_idx ON social_publish_accounts(tenant_id, platform);
CREATE UNIQUE INDEX social_publish_account_sau_account_id_uk ON social_publish_accounts(sau_account_id);
CREATE INDEX  social_publish_account_status_idx ON social_publish_accounts(status);
```

> **命名说明**：表名遵循项目约定（snake_case 复数）；与设计文档单数 `social_publish_account` 略有差异，
> 与既有 `creator_works`、`payment_orders` 风格一致。

### A.2 Alembic 文件骨架

文件名：`api/migrations/versions/2026_04_18_1000-<新生成的 12 位 hash>_add_social_publish_account.py`

```python
"""add social_publish_accounts table

Revision ID: <12位hash>
Revises: cbc30aed1134       # 当前 head: SMS 那条 migration
Create Date: 2026-04-18 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "<12位hash>"
down_revision = "cbc30aed1134"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "social_publish_accounts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("sau_account_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending_auth"),
        sa.Column("last_check_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="social_publish_account_pkey"),
    )
    op.create_index(
        "social_publish_account_tenant_platform_idx",
        "social_publish_accounts",
        ["tenant_id", "platform"],
    )
    op.create_index(
        "social_publish_account_sau_account_id_uk",
        "social_publish_accounts",
        ["sau_account_id"],
        unique=True,
    )
    op.create_index(
        "social_publish_account_status_idx",
        "social_publish_accounts",
        ["status"],
    )


def downgrade():
    op.drop_index("social_publish_account_status_idx", table_name="social_publish_accounts")
    op.drop_index("social_publish_account_sau_account_id_uk", table_name="social_publish_accounts")
    op.drop_index("social_publish_account_tenant_platform_idx", table_name="social_publish_accounts")
    op.drop_table("social_publish_accounts")
```

> **生成 hash**：执行 `uv run --project api alembic -c migrations/alembic.ini revision -m "add social_publish_accounts"` 取自动生成的 hash 替换占位符。

---

## B. SQLAlchemy Model 字段定义

文件：`api/models/social_publish.py`

```python
"""Social publish models.

Includes:
- SocialPublishAccount: 抖音/小红书/快手发布账号映射
"""
import enum
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import StringUUID


class SocialPublishPlatform(enum.StrEnum):
    DOUYIN = "douyin"
    XHS = "xhs"      # 占位，P4 启用
    KS = "ks"        # 占位，P4 启用


class SocialPublishAccountStatus(enum.StrEnum):
    PENDING_AUTH = "pending_auth"
    ACTIVE = "active"
    EXPIRED = "expired"


class SocialPublishAccount(TypeBase):
    """绑定到平台账号（抖音/小红书/快手）的映射表，按 tenant 隔离。"""

    __tablename__ = "social_publish_accounts"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="social_publish_account_pkey"),
        sa.Index("social_publish_account_tenant_platform_idx", "tenant_id", "platform"),
        sa.Index("social_publish_account_sau_account_id_uk", "sau_account_id", unique=True),
        sa.Index("social_publish_account_status_idx", "status"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    sau_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    avatar_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
    status: Mapped[str] = mapped_column(
        String(16), server_default=SocialPublishAccountStatus.PENDING_AUTH.value,
        default=SocialPublishAccountStatus.PENDING_AUTH.value,
    )
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
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
            "platform": self.platform,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "status": self.status,
            "last_check_at": self.last_check_at.isoformat() if self.last_check_at else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<SocialPublishAccount id={self.id} tenant={self.tenant_id} "
            f"platform={self.platform} status={self.status}>"
        )
```

> 依旧使用 `TypeBase` 与 `StringUUID`，与 `creator_works` 风格一致。`tenant_id` 不进 `to_dict()`，避免向前端泄漏。

---

## C. Repository 设计

### C.1 Protocol（`api/repositories/social_publish_account_repository.py`）

```python
"""SocialPublishAccount Repository Protocol.

Service-layer interface for social_publish_accounts table.
All methods enforce tenant isolation via the tenant_id parameter.
"""
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from models.social_publish import SocialPublishAccount


class SocialPublishAccountRepository(Protocol):
    """Repository for social_publish_accounts."""

    def create(
        self,
        *,
        tenant_id: str,
        platform: str,
        sau_account_id: str,
        display_name: str | None,
        avatar_url: str | None,
        status: str,
        created_by: str,
    ) -> SocialPublishAccount: ...

    def get_by_id_and_tenant(
        self, account_id: str, tenant_id: str,
    ) -> SocialPublishAccount | None:
        """带 tenant 隔离的单查；任何 service 调用都必须走这条路。"""
        ...

    def get_by_sau_account_id(self, sau_account_id: str) -> SocialPublishAccount | None:
        """sau 回调时查询用；service 层取到对象后必须再次校验 tenant。"""
        ...

    def list_by_tenant(
        self,
        tenant_id: str,
        platform: str | None = None,
    ) -> Sequence[SocialPublishAccount]: ...

    def update_status(
        self,
        account_id: str,
        tenant_id: str,
        status: str,
        last_check_at: datetime | None = None,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> SocialPublishAccount | None:
        """部分更新（profile / 状态）。tenant_id 作为 where 条件防越权。"""
        ...

    def delete_by_id_and_tenant(self, account_id: str, tenant_id: str) -> bool:
        """返回是否实际删除了一行。"""
        ...
```

### C.2 实现要点（`api/repositories/sqlalchemy_social_publish_account_repository.py`）

- 构造函数注入 `sessionmaker[Session]`，不直接用全局 `db.session`
- 所有读写都走 `with self._session_maker() as session:`，写操作显式 `session.commit()`
- `update_status` / `delete_by_id_and_tenant` 必须把 `tenant_id` 写进 `WHERE`，
  并通过 `result.rowcount` 判断是否真的命中（防越权静默失败）
- `list_by_tenant` 默认按 `created_at DESC` 排序
- 实现类命名：`DifyAPISQLAlchemySocialPublishAccountRepository`，与现有命名一致

### C.3 Factory 改动

在 `api/repositories/factory.py` `DifyAPIRepositoryFactory` 类内追加：

```python
@classmethod
def create_social_publish_account_repository(
    cls, session_maker: sessionmaker[Session],
) -> SocialPublishAccountRepository:
    class_path = dify_config.API_SOCIAL_PUBLISH_ACCOUNT_REPOSITORY
    try:
        repository_class = import_string(class_path)
        return repository_class(session_maker=session_maker)
    except (ImportError, Exception) as e:
        raise RepositoryImportError(
            f"Failed to create SocialPublishAccountRepository from '{class_path}': {e}"
        ) from e
```

并在 `api/configs/feature/__init__.py` 增加配置项：

```python
API_SOCIAL_PUBLISH_ACCOUNT_REPOSITORY: str = Field(
    default="repositories.sqlalchemy_social_publish_account_repository.DifyAPISQLAlchemySocialPublishAccountRepository",
    description="Class path of SocialPublishAccountRepository implementation",
)
```

---

## D. Service 设计

### D.1 文件：`api/services/social_publish_service.py`

```python
class SocialPublishService:
    """业务编排：组合 repository + sau client，执行 tenant 隔离校验。"""

    def __init__(
        self,
        *,
        repository: SocialPublishAccountRepository,
        sau_client: SauClient,
    ) -> None:
        self._repo = repository
        self._sau = sau_client

    # ---------- 账号查询 ----------
    def list_accounts(self, tenant_id: str, platform: str | None = None) -> list[SocialPublishAccount]: ...

    def get_account(self, account_id: str, tenant_id: str) -> SocialPublishAccount:
        """找不到 → AccountNotFoundError；存在但 tenant 不匹配 → TenantMismatchError。"""
        ...

    # ---------- 扫码授权 ----------
    def start_auth(self, *, tenant_id: str, platform: str, account_id: str) -> AuthStartResponse:
        """
        1. 校验 platform == "douyin"，否则 PlatformUnsupportedError
        2. 生成 session_id (uuid4)
        3. 在 Redis 写入初始状态：
             key  = f"sau:auth:{session_id}"
             ttl  = 200 秒（设计文档 180s + 20s 缓冲）
             body = {tenant_id, platform, status="waiting", created_at, account_id}
        4. 调 sau /login 拿 qr_base64：传 tenant_id/platform/session_id（同时把 callback URL 给 sau）
        5. 返回 {session_id, qr_image_base64, expires_in: 180}
        """
        ...

    def get_auth_status(self, session_id: str, tenant_id: str) -> AuthStatusResponse:
        """
        1. 从 Redis 读 session，找不到 → SessionExpiredError
        2. 校验 session.tenant_id == tenant_id（防越权偷看别人的扫码进度）
        3. 若 status 仍是 waiting/scanned，调 sau GET /login/status/{session_id} 拉最新进度
           - 写回 Redis（保持 ttl）
        4. 若 sau 返回 success，且本地无对应 account → repository.create()
           （以 sau_account_id 去重；并发场景吃 unique 约束 → 转 update_status）
        5. 返回 {status, account?, message?}
        """
        ...

    # ---------- 账号删除 ----------
    def delete_account(self, account_id: str, tenant_id: str) -> None:
        """
        1. get_account()（隐含 tenant 校验）
        2. 调 sau POST /accounts/{sau_account_id}/delete（异常吞掉但写日志：
           sau 删失败不应阻塞 Dify 端清理，cookie 文件可由后续清理任务处理）
        3. repository.delete_by_id_and_tenant() ；rowcount==0 → TenantMismatchError
        """
        ...
```

### D.2 关键不变量

- **任何修改/删除/查询单行的方法**都必须把 `tenant_id` 当 `WHERE` 条件，**不允许**先查后判断（TOCTOU 风险）
- `get_account` 找到对象后**必须**比较 `obj.tenant_id == tenant_id`，**不一致就抛 `TenantMismatchError`**
  （理论上 repository 已经按 tenant 过滤了；这里是双保险）
- sau 调用失败必须分类抛错：网络/超时 → `SauUnreachableError`，HTTP 4xx/5xx → `SauApiError`
- service 永远不直接 `db.session.*`，全部走 repository

### D.3 DTO（dataclasses）

```python
@dataclass(frozen=True)
class AuthStartResponse:
    session_id: str
    qr_image_base64: str
    expires_in: int

@dataclass(frozen=True)
class AuthStatusResponse:
    status: str          # waiting | scanned | success | expired | failed
    account: dict | None # to_dict() 形式
    message: str | None
```

---

## E. Controller 路由 + Schema

### E.1 文件结构

```
api/controllers/console/social_publish/
├── __init__.py            # from . import accounts
├── error.py               # HTTP 异常映射
└── accounts.py            # 4 个 REST 接口
```

并在 `api/controllers/console/__init__.py` 中：

1. `from .social_publish import accounts as social_publish_accounts`
2. 把 `/console/api/social-publish/` 加入 `_CREATOR_ALLOWED_PREFIXES`（与 `/console/api/creator/` 同级）
3. 模块名加入 `__all__`

### E.2 路由表

| Method | Path | 鉴权装饰器 | 说明 |
|---|---|---|---|
| GET | `/console/api/social-publish/accounts` | setup_required + login_required + account_initialization_required | 列表（按当前 tenant） |
| POST | `/console/api/social-publish/accounts/auth/start` | 同上 | 启动扫码 |
| GET | `/console/api/social-publish/accounts/auth/status/<session_id>` | 同上 | 轮询授权状态 |
| DELETE | `/console/api/social-publish/accounts/<id>` | 同上 | 删除账号 |

> 与 `creator/works.py` 一致使用 `current_account_with_tenant()` 拿 `current_tenant_id`。

### E.3 Request / Response Schema

**GET /accounts**

- Query: `platform=douyin`（可选）
- Resp 200:
  ```json
  {
    "data": [
      {"id":"<uuid>", "platform":"douyin", "display_name":"小妹",
       "avatar_url":"https://...", "status":"active",
       "last_check_at":"2026-04-18T03:00:00", "created_at":"..."}
    ]
  }
  ```

**POST /accounts/auth/start**

- Body: `{"platform": "douyin"}`
- Resp 200:
  ```json
  {"session_id":"<uuid>", "qr_image_base64":"data:image/png;base64,...",
   "expires_in":180}
  ```
- Errors: 400 `platform_unsupported`、502 `sau_unreachable`、503 `feature_disabled`

**GET /accounts/auth/status/{session_id}**

- Resp 200:
  ```json
  {"status":"success",
   "account":{"id":"<uuid>","platform":"douyin","display_name":"小妹",...},
   "message":null}
  ```
- 状态枚举：`waiting | scanned | success | expired | failed`
- Errors: 404 `session_expired`、403 `tenant_mismatch`

**DELETE /accounts/{id}**

- Resp 200: `{"result": "success"}`
- Errors: 404 `account_not_found`、403 `tenant_mismatch`

### E.4 Controller 写法约定

- **不**在 controller 内拼 SQL；所有数据访问交给 service
- 在 controller 顶部统一构造 `service`（用 `DifyAPIRepositoryFactory` + `SauClient` 单例）
- 异常通过 `controllers/console/social_publish/error.py` 映射成 Werkzeug HTTP 异常
- 响应统一裹 `{"data": ...}` 或单对象，沿用项目现有风格（参考 `creator/works.py`）

---

## F. SAU Client 设计

文件：`api/services/sau_client.py`

### F.1 配置项

`api/configs/feature/__init__.py` 与 `api/.env.example` 新增：

```
SAU_BASE_URL=http://sau-api:8001
SAU_INTERNAL_TOKEN=                       # 必填，未配置则 feature 自动关闭
SAU_HTTP_TIMEOUT_SECONDS=10               # connect+read 总时长
SAU_HTTP_MAX_RETRIES=2                    # 仅对 5xx / 网络抖动重试
SAU_HTTP_POOL_SIZE=20
SOCIAL_PUBLISH_ENABLED=false              # P1 默认关，灰度后开
```

### F.2 客户端骨架

```python
class SauClient:
    """HTTPX-based client for the sau service.

    线程安全：底层 httpx.Client 自带连接池，复用一个全局实例。
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        max_retries: int,
        pool_size: int,
    ) -> None:
        if not token:
            raise RuntimeError("SAU_INTERNAL_TOKEN missing")
        limits = httpx.Limits(max_connections=pool_size, max_keepalive_connections=pool_size)
        self._client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            limits=limits,
            headers={"X-Sau-Token": token, "User-Agent": "dify-api/sau-client"},
        )
        self._max_retries = max_retries

    # ---------- 公开 API ----------
    def start_login(self, *, tenant_id: str, platform: str, session_id: str) -> SauLoginInitResponse:
        """POST /login → {qr_base64}"""

    def get_login_status(self, *, session_id: str) -> SauLoginStatusResponse:
        """GET /login/status/{session_id}
        → {status, account_id?, profile?}"""

    def check_account(self, *, sau_account_id: str) -> SauCheckResponse:
        """POST /accounts/{sau_account_id}/check → {valid, checked_at}"""

    def delete_account(self, *, sau_account_id: str) -> None:
        """POST /accounts/{sau_account_id}/delete"""

    # ---------- 私有 ----------
    def _request(self, method: str, path: str, **kw) -> dict:
        """统一重试 + 错误转换。"""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.request(method, path, **kw)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                last_exc = e
                if attempt == self._max_retries:
                    raise SauUnreachableError(str(e)) from e
                time.sleep(0.2 * (2 ** attempt))   # 指数退避：0.2s / 0.4s
                continue

            if 500 <= resp.status_code < 600 and attempt < self._max_retries:
                time.sleep(0.2 * (2 ** attempt))
                continue

            if resp.status_code >= 400:
                raise SauApiError(resp.status_code, resp.text)
            return resp.json()
        raise SauUnreachableError(str(last_exc) or "unknown")

    def close(self) -> None:
        self._client.close()
```

### F.3 设计要点

| 关注点 | 处理 |
|---|---|
| 鉴权 | `X-Sau-Token` header 在 `httpx.Client` 默认 headers 上，不会漏注入 |
| 连接池 | 用 `httpx.Limits(max_connections=20)`，复用单例（在 service 工厂里创建） |
| 超时 | 单次请求总超时 10s；扫码 SSE/长 polling **不在 P1 范围**，所有调用都是短请求 |
| 重试 | 仅对网络异常 + 5xx 重试 2 次（总共 3 次），指数退避；4xx 立即抛 |
| 单例化 | 在 app 启动时初始化一次（`extensions/ext_sau_client.py` 风格），controller 只取不创建 |
| 关闭 | Flask teardown_appcontext 不需要每请求 close；进程退出时 `atexit.register(client.close)` |
| Token 校验 | 启动时如果 `SAU_INTERNAL_TOKEN` 为空 → `social_publish_enabled` 强制 False |

---

## G. 错误码定义

### G.1 领域异常（`api/services/errors/social_publish.py`）

```python
class SocialPublishError(Exception):
    """Base."""
    code = "social_publish_error"

class FeatureDisabledError(SocialPublishError):
    code = "feature_disabled"

class PlatformUnsupportedError(SocialPublishError):
    code = "platform_unsupported"

class AccountNotFoundError(SocialPublishError):
    code = "account_not_found"

class TenantMismatchError(SocialPublishError):
    code = "tenant_mismatch"

class AccountExpiredError(SocialPublishError):
    code = "account_expired"

class SessionExpiredError(SocialPublishError):
    code = "session_expired"

class SauUnreachableError(SocialPublishError):
    code = "sau_unreachable"

class SauApiError(SocialPublishError):
    code = "sau_api_error"
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"sau {status_code}: {body[:200]}")
        self.status_code = status_code
```

### G.2 HTTP 映射（`api/controllers/console/social_publish/error.py`）

| 异常 | HTTP | code（response body） |
|---|---|---|
| `FeatureDisabledError` | 503 | `feature_disabled` |
| `PlatformUnsupportedError` | 400 | `platform_unsupported` |
| `AccountNotFoundError` | 404 | `account_not_found` |
| `TenantMismatchError` | 403 | `tenant_mismatch` |
| `AccountExpiredError` | 409 | `account_expired` |
| `SessionExpiredError` | 404 | `session_expired` |
| `SauUnreachableError` | 502 | `sau_unreachable` |
| `SauApiError` | 502 | `sau_api_error` |

实现方式：参考 `controllers/console/auth/error.py`，继承 `werkzeug.exceptions.HTTPException`，设置
`code` 与 `description`，让 Flask 自动序列化。

### G.3 错误响应体

```json
{"code": "tenant_mismatch", "message": "...", "status": 403}
```

与项目现有 `console_ns` 错误格式保持一致。

---

## H. 单元测试清单（TDD red 阶段先写）

### H.1 Repository 层（`tests/unit_tests/repositories/test_social_publish_account_repository.py`）

> 用内存 SQLite + sessionmaker，按 AAA 模式

1. `test_create_inserts_row_with_pending_auth_status`
2. `test_get_by_id_and_tenant_returns_none_for_other_tenant` ← **隔离 case**
3. `test_list_by_tenant_filters_by_platform`
4. `test_update_status_returns_none_when_tenant_mismatch` ← **隔离 case**
5. `test_delete_by_id_and_tenant_returns_false_for_other_tenant` ← **隔离 case**
6. `test_get_by_sau_account_id_returns_globally`（不带 tenant 过滤；用于回调）

### H.2 Service 层（`tests/unit_tests/services/test_social_publish_service.py`）

> mock `SocialPublishAccountRepository` Protocol + mock `SauClient`

1. `test_get_account_raises_tenant_mismatch_when_object_belongs_to_other_tenant`
2. `test_start_auth_rejects_unsupported_platform`
3. `test_start_auth_writes_session_to_redis_with_180s_ttl`
4. `test_get_auth_status_creates_account_when_sau_returns_success`
5. `test_get_auth_status_rejects_when_session_tenant_does_not_match_caller`  ← **隔离 case**
6. `test_delete_account_calls_sau_then_repository`
7. `test_start_auth_propagates_sau_unreachable_error`

### H.3 SAU Client 层（`tests/unit_tests/services/test_sau_client.py`）

> 用 `respx` 或 `httpx.MockTransport` 替代真实网络

1. `test_x_sau_token_header_injected_on_every_request`
2. `test_retries_twice_on_5xx_then_succeeds`
3. `test_raises_sau_unreachable_after_max_retries_on_network_error`
4. `test_does_not_retry_on_4xx`
5. `test_timeout_propagates_as_sau_unreachable`

### H.4 Controller 层（`tests/unit_tests/controllers/console/social_publish/test_accounts.py`）

> 复用 `tests/unit_tests/controllers/console/test_workspace_account.py` 的 Flask test client + login fixture

1. `test_list_accounts_returns_only_current_tenant_rows` ← **隔离 case**
2. `test_post_auth_start_returns_session_id_and_qr`
3. `test_get_auth_status_returns_403_for_session_owned_by_other_tenant` ← **隔离 case**
4. `test_delete_account_returns_404_when_account_belongs_to_other_tenant` ← **隔离 case**
5. `test_endpoints_return_503_when_feature_disabled`
6. `test_unauthenticated_request_returns_401`

**最低覆盖率目标**：service 90%、repository 90%、controller 80%、sau_client 85%。

---

## I. 隔离测试场景（A 用户访问 B 用户账号）

汇总跨层的强隔离 case，**每条都要写 happy + isolation 两份**：

| # | 场景 | 期望 |
|---|---|---|
| I-1 | tenant A 调用 GET /accounts，结果中不能出现 tenant B 的任何 account | response.data 长度 == A 的 row 数 |
| I-2 | tenant A 用 tenant B 的 account.id 调用 DELETE | 404 `account_not_found`（不区分"不存在"和"不是你的"，防探测） |
| I-3 | tenant A 用 tenant B 的 session_id 调用 GET /auth/status | 403 `tenant_mismatch`（session_id 已知但 tenant 不匹配） |
| I-4 | tenant A 在 sau 回调创建 account 时，bypass 走捷径试图绑定 tenant B 的 account_id | service 拒绝，repository unique 约束兜底 |
| I-5 | 直接调 repository.update_status 传错误 tenant_id | 返回 None，DB 行不变 |
| I-6 | sau 返回的 sau_account_id 已被另一 tenant 占用 | `IntegrityError` → 转 `SauApiError` 抛出，不会污染 A 的数据 |

**实现方式**：

- I-1 / I-2 / I-3 / I-6 → controller test（用 fixture 创建 2 个 tenant、2 套登录态）
- I-4 / I-5 → service / repository test（直接 mock）

---

## J. 工作量估算（按小时）

| 任务 | 估时 (h) | 依赖 |
|---|---|---|
| 1. Alembic 迁移 + 在本地起库验证 upgrade/downgrade | 2 | — |
| 2. SQLAlchemy model + `__repr__` + to_dict + 跑 `alembic check` | 2 | 1 |
| 3. Repository Protocol + SQLAlchemy 实现 + factory 接入 | 4 | 2 |
| 4. Repository 单测（6 case） | 3 | 3 |
| 5. SAU client：HTTPX 客户端 + 重试 + 单例 + atexit | 4 | — |
| 6. SAU client 单测（5 case，需引入 respx） | 3 | 5 |
| 7. 领域异常 + HTTP 错误映射 | 2 | — |
| 8. Service 层：DTO + 4 个公开方法 + Redis session 状态机 | 6 | 3, 5, 7 |
| 9. Service 单测（7 case，含隔离） | 4 | 8 |
| 10. Controller：4 个接口 + 装饰器 + 路由注册 | 4 | 8 |
| 11. Controller 单测（6 case，含隔离） | 4 | 10 |
| 12. feature_service 加 `social_publish_enabled` + 接入 controller 拦截 | 2 | — |
| 13. .env.example + dify_config 字段 + README 段落 | 1 | — |
| 14. 联调：起 sau-mock（用 FastAPI 起最小 stub）跑通完整扫码闭环 | 4 | 10, 5 |
| 15. 自测覆盖率 + ruff/black/mypy 修复 | 2 | 全部 |
| 16. 隔离专项测试 review + 补漏（I-1~I-6） | 2 | 11 |
| 17. PR 自审 + commit 拆分 | 1 | 全部 |
| **合计** | **50** | ≈ **6.25 人日**（按 8h/天） |

> Buffer 建议：20% → **7.5 人日**，与设计文档 P1 的 4-6 天估算基本吻合（设计文档假设有 sau-mock 现成）。

---

## SSE → 轮询的具体落地

设计文档 §4.1 已声明用轮询替代 SSE，下面给出 P1 的具体做法：

1. **session_id 的产生**：service 层 `start_auth` 用 `uuid4()` 生成，无碰撞风险
2. **Redis Key**：`sau:auth:{session_id}`，TTL 200s（前端按 180s 倒计时，留 20s 缓冲给最后一次轮询）
3. **Redis Value (JSON)**：
   ```json
   {
     "tenant_id": "...",
     "platform": "douyin",
     "status": "waiting|scanned|success|expired|failed",
     "sau_account_id": null,
     "profile": null,
     "updated_at": "..."
   }
   ```
4. **前端轮询**：每 2s 调一次 `GET /auth/status/{session_id}`，最多 90 次（180s）
5. **后端响应**：service 每次被调用时
   - 先读 Redis；TTL 过期 → 返回 `expired`（同时清 Redis）
   - 校验 session.tenant_id == 调用者 tenant_id（防越权）
   - 若状态仍是 `waiting/scanned`，**主动**调一次 sau `GET /login/status/{session_id}`，
     用 sau 返回更新 Redis；这样前端轮询的延迟上限 = sau 内部刷新间隔 + 2s
   - 若 sau 返回 `success`：service 同步把 account 落库（如果还没落），
     刷新 Redis 状态为 `success`，下次轮询前端就能拿到 account 详情
6. **sau 端的契约**（写到 sau 仓库的 P1 issue）：
   - `POST /login` 启动后，**不阻塞**返回 qr，把扫码循环放到 sau 内部协程
   - 每次状态变化把最新结果写到 sau 自己的 in-memory dict，按 session_id 查
   - 提供 `GET /login/status/{session_id}` 同步返回当前状态
   - 这样 SSE → 普通 HTTP，nginx/gunicorn 60s 超时不再是问题

> **优势**：
> - Dify api 进程**完全无状态**，不持有任何长连接
> - 多 worker 部署天然 OK（Redis 共享 session）
> - sau 重启只丢 in-memory 的 SSE 进度，下次轮询发现 session 还在 Redis 但 sau 不认 → 标 `failed` 让前端重启

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| sau 服务不可达 | 扫码全挂 | client 自动重试 2 次 + feature flag 可一键关掉发布中心入口 |
| sau_account_id 全局唯一约束撞车（多租户共用 sau） | 创建账号失败 | 让 sau 在 `tenant_id` 维度生成唯一 ID（设计文档已约定）；Dify 兜底捕 IntegrityError |
| Redis 挂了 | 扫码全挂、tier 缓存失效 | 跟 Dify 现有 Redis 同生共死，本期不引入额外 fallback |
| 前端反复轮询打挂 sau | sau /login/status 被刷爆 | controller 层加 `@rate_limit(per_user, 1/s)`（用现有装饰器） |
| 用户在 A workspace 绑了号、切到 B 后还能看到 | 数据泄漏（CRITICAL） | I-1~I-6 隔离 case 必须全绿才能合并 |
| HTTPX client 句柄泄漏 | 文件描述符耗尽 | 单例 + atexit close；单测断言只创建一次 |

---

## Success Criteria

- [ ] Alembic upgrade/downgrade 双向跑通
- [ ] `social_publish_enabled` flag 关闭时所有接口返回 503
- [ ] 单元测试 ≥ 80% 覆盖率（service ≥ 90%）
- [ ] 6 条隔离测试 case 全绿
- [ ] sau 不可达时前端能拿到 502 + `sau_unreachable`，不报 500
- [ ] 抖音扫码全链路在 mock sau 下能跑通：start → polling 90 次内拿到 success → 列表里出现新账号 → 删除消失
- [ ] 通过 `pnpm` 等价的 lint/type-check：`uv run --project api ruff check .`、`uv run --project api mypy .`
- [ ] PR 自查：无硬编码 token、无 `print()`、无 `Any`、所有函数 ≤ 50 行、所有文件 ≤ 800 行
