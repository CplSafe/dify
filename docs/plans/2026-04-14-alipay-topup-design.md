# 支付宝充值 + 工作空间钱包体系 设计文档

**日期**：2026-04-14
**作者**：协同设计稿（用户 + Claude）
**状态**：已敲定，待实施

---

## 1. 背景与目标

### 1.1 现状

- 已有完整的扣费机制：`UserBilling Service.deduct_for_workflow_run()` 在 workflow 跑完后按 token 计费扣 `UserBalance`
- 已有账本表 `BillingRecord`，类型有 `deduction / topup / rebate`
- 充值目前**只能由超管手动调用** `topup()`，缺自助充值入口
- `BillingService`（外部 SaaS 订阅）与本设计**无关**，本设计聚焦自有钱包

### 1.2 目标

1. **自助充值**：用户通过支付宝扫码支付为工作空间钱包充值
2. **两级钱包**：工作空间钱包（Tenant 级）+ 成员钱包（Account 级）
3. **预算分配**：owner/admin 把钱包额度分配给成员，单向可回收
4. **完整账本**：充值、分配、消费、返点全程可追溯
5. **安全**：签名验证、幂等回调、大额告警
6. **可扩展**：抽象 `PaymentProvider` 接口，预留微信支付接入点

### 1.3 非目标

- 不做发票
- 不做退款 UI（管理员可走支付宝后台手动退款，本系统记录日志即可）
- 不做订阅/套餐（仍按现有 token 计费模型）

---

## 2. 资金模型

### 2.1 两级钱包

```
TenantBalance（工作空间钱包）
  ├─ owner/admin 充值（走支付宝）
  ├─ owner/admin 分配/回收给成员
  └─ 余额耗尽时整个空间停服

UserBalance（成员钱包，沿用现有表）
  ├─ 由 owner 从 Tenant 钱包划入
  ├─ workflow 消费时扣这里
  └─ 余额耗尽时该成员停服
```

### 2.2 资金流向

```
支付宝 ──→ TenantBalance.balance
              │
              │ owner allocate +N
              ▼
         TenantBalance.locked  ←──→  UserBalance.balance
              │                          │
              │   workflow 消费 -amount  │
              ▼                          ▼
         locked -= amount           balance -= amount
                                         │
                                  写两条 BillingRecord
                                  (scope=tenant + scope=user)
```

### 2.3 关键不变式（任意时刻成立）

1. `Σ(所有成员 UserBalance.balance) == TenantBalance.locked`
2. `TenantBalance.balance >= 0` 且 `TenantBalance.locked >= 0`
3. `UserBalance.balance >= 0`（不可负，预算用完即停）
4. `TenantBalance.total_topup == Σ(所有 paid PaymentOrder.amount)`

### 2.4 资金动作汇总表

| 动作 | TenantBalance | UserBalance | BillingRecord |
|---|---|---|---|
| 充值（支付宝回调成功） | `balance += amount`<br>`total_topup += amount` | — | `topup` (scope=tenant) |
| 分配 owner→成员 +N | `balance -= N`<br>`locked += N` | `balance += N` | `allocation` (scope=user) |
| 回收 owner←成员 -N | `balance += N`<br>`locked -= N` | `balance -= N` | `allocation` (scope=user, amount<0) |
| 消费（workflow 完成） | `locked -= amount` | `balance -= amount` | `deduction` × 2 (tenant + user) |
| 返点（每日结算） | — | 邀请人 `balance += rebate` | `rebate` (scope=user) |

### 2.5 个人 Tenant 自动分配

注册时每个账户自动创建一个个人 Tenant（owner=自己，唯一成员）。这种场景：

- 充值进 TenantBalance 后，**自动一次性 100% 分配**给 owner 自己
- UI 隐藏分配模块，体感为"充值即可用"
- 实现：`PaymentService.handle_alipay_notify()` 入账后判断 `Tenant.member_count == 1 && operator == owner` → 触发 `auto_allocate_to_owner()`

### 2.6 可用性检查

```python
def can_run_workflow(account_id, tenant_id) -> tuple[bool, ErrorCode | None]:
    user = UserBalance.get(account_id)
    if user.balance <= 0:
        return False, "INSUFFICIENT_USER_BUDGET"
    return True, None
```

> 由不变式 1，`UserBalance > 0` 隐含 `TenantBalance.locked > 0`，故只查一处。错误信息分两种：
> - 个人额度用完 → "您的可用额度已用完，请联系空间管理员分配"
> - Tenant 余额不足（owner 自己用时） → "工作空间余额不足，请充值"

---

## 3. 数据模型

### 3.1 新增表

#### `tenant_balances`

```python
class TenantBalance(TypeBase):
    __tablename__ = "tenant_balances"
    __table_args__ = (
        sa.Index("tenant_balance_tenant_id_idx", "tenant_id", unique=True),
    )
    id: Mapped[str] = mapped_column(StringUUID, ...)
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    balance: Mapped[Decimal]      # 可分配余额
    locked: Mapped[Decimal]       # 已分配未消费
    total_topup: Mapped[Decimal]  # 累计充值
    currency: Mapped[str] = "CNY"
    created_at / updated_at

    @property
    def total(self) -> Decimal:
        return self.balance + self.locked
```

#### `payment_orders`

```python
class PaymentOrder(TypeBase):
    __tablename__ = "payment_orders"
    __table_args__ = (
        sa.Index("payment_order_out_trade_no_idx", "out_trade_no", unique=True),
        sa.Index("payment_order_tenant_status_idx", "tenant_id", "status"),
        sa.Index("payment_order_provider_trade_idx", "provider", "provider_trade_no"),
    )
    id: UUID
    provider: str                # "alipay" | "wechat"（预留）
    out_trade_no: str(64)        # 我方订单号，幂等键
    provider_trade_no: str(64) | None  # 支付宝 trade_no
    tenant_id: str
    account_id: str              # 发起人
    amount: Decimal              # 元
    amount_fen: int              # 分（实际对接支付宝）
    subject: str(256)            # "工作空间充值 - {tenant_name}"
    status: str                  # pending | paid | closed | refunded | failed
    qr_code: str(512) | None     # 支付宝返回二维码字符串
    prepay_raw: Text             # precreate 返回原文（审计）
    notify_raw: Text | None      # 异步通知原文（审计）
    paid_at: datetime | None
    expires_at: datetime
    client_ip: str(64) | None
    created_at / updated_at
```

#### `allocation_records`

```python
class AllocationRecord(TypeBase):
    __tablename__ = "allocation_records"
    __table_args__ = (
        sa.Index("alloc_tenant_created_idx", "tenant_id", "created_at"),
        sa.Index("alloc_member_idx", "account_id"),
    )
    id: UUID
    tenant_id: str
    account_id: str              # 目标成员
    operator_id: str             # 操作人（owner/admin）
    amount: Decimal              # 正=分配 / 负=回收
    description: str | None
    created_at
```

### 3.2 现有模型变更

#### `BillingRecord` 增加 `scope`

```python
scope: Mapped[str] = mapped_column(String(20), server_default="user")  # "tenant" | "user"
```

新增枚举值：
```python
class BillingRecordType(enum.StrEnum):
    DEDUCTION = "deduction"
    TOPUP = "topup"
    REBATE = "rebate"
    ALLOCATION = "allocation"  # 新增
```

#### `UserBalance` 不动

保留所有现有字段。语义从"账户钱包"变为"被分配的预算余额"。

---

## 4. 支付宝集成（当面付 / 扫码支付）

### 4.1 SDK

`alipay-sdk-python`（官方）：
```bash
uv add alipay-sdk-python
```

### 4.2 配置

环境变量放 `api/.env`，私钥/公钥用 PEM 文件挂载：

```bash
# api/.env
ALIPAY_ENABLED=true
ALIPAY_APP_ID=2021xxxxxxxxxxxx
ALIPAY_USE_SANDBOX=false
ALIPAY_GATEWAY=https://openapi.alipay.com/gateway.do
ALIPAY_SIGN_TYPE=RSA2
ALIPAY_NOTIFY_URL=https://api.your-domain.com/console/api/billing/alipay/notify

ALIPAY_MIN_AMOUNT_FEN=100
ALIPAY_ORDER_TIMEOUT_MIN=15
ALIPAY_LARGE_AMOUNT_THRESHOLD=5000

ALIPAY_APP_PRIVATE_KEY_PATH=/app/secrets/alipay/app_private_key.pem
ALIPAY_PUBLIC_KEY_PATH=/app/secrets/alipay/alipay_public_key.pem
```

私钥文件目录 `api/secrets/alipay/` 加入 `.gitignore`，生产用 K8s Secret 挂载。

### 4.3 配置加载（pydantic settings）

```python
# api/configs/feature/__init__.py
class AlipayConfig(BaseSettings):
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

启动时校验：`ALIPAY_ENABLED=true` 时强制 `APP_ID / 私钥 / 公钥 / NOTIFY_URL` 不为空，缺则 fail-fast。

### 4.4 服务层结构

```
api/services/payment/
├── __init__.py
├── base.py                  # PaymentProvider Protocol + DTO
├── alipay/
│   ├── __init__.py
│   ├── client.py            # 封装 alipay-sdk-python，单例
│   ├── provider.py          # AlipayProvider implements PaymentProvider
│   └── signature.py         # 双保险验签
├── service.py               # PaymentService：业务编排
├── alerts.py                # PaymentAlertService：大额告警
└── exceptions.py
```

### 4.5 抽象接口

```python
class PaymentProvider(Protocol):
    name: str
    def create_qr_order(self, *, out_trade_no, amount_fen, subject, notify_url) -> str: ...
    def query_order(self, *, out_trade_no) -> ProviderOrderStatus: ...
    def verify_notify(self, *, params: dict) -> bool: ...
    def parse_notify(self, *, params: dict) -> NotifyPayload: ...
```

未来接微信只需实现 `WechatProvider`，`PaymentService` 不动。

### 4.6 业务流程时序

```
[前端]                 [后端]                 [支付宝]                [DB]
  POST /topup          │                       │                       │
  {amount:100}         │                       │                       │
─────────────────────► │                       │                       │
                       │ 1. 校验 owner/admin                            │
                       │ 2. 校验金额 ≥ 1元                              │
                       │ 3. 限流：5次/min/account                       │
                       │ 4. 生成 out_trade_no = uuid+ts                 │
                       │ INSERT order(pending) ─────────────────────► │
                       │ 5. alipay.trade.precreate                      │
                       ├─────────────────────► │                       │
                       │ ◄──── qr_code ────────│                       │
                       │ UPDATE order.qr_code ──────────────────────► │
  ◄── qr_code ─────────│                       │                       │
  渲染二维码           │                       │                       │
  轮询 /order/:id 2s   │                       │                       │
─────────────────────► │ (查 DB,pending 时主动查支付宝兜底,限频 30s/次) │
                       │   用户扫码付款 ─────► │                       │
                       │                       │   支付完成 ─异步通知─►│
                       │ ◄── POST notify ──────│                       │
                       │ 1. RSA2 验签                                   │
                       │ 2. app_id 校验                                 │
                       │ 3. SELECT FOR UPDATE order                     │
                       │ 4. trade_status == TRADE_SUCCESS               │
                       │ 5. total_amount == order.amount                │
                       │ 6. 已 paid? → return 'success'                 │
                       │ 7. 事务：                                       │
                       │    - UPDATE order(paid)                        │
                       │    - UPDATE TenantBalance.balance += amount    │
                       │    - INSERT BillingRecord(topup,scope=tenant)  │
                       │ 8. 个人 Tenant: auto_allocate_to_owner         │
                       │ 9. 大额告警检查                                │
                       ├── 'success' ────────► │                       │
  下次轮询 → paid     │                       │                       │
  关闭弹窗 + 提示成功  │                       │                       │
```

### 4.7 回调安全（9 条）

1. **HTTPS 强制**：notify_url 必须 https
2. **RSA2 验签**：用 `ALIPAY_PUBLIC_KEY` 验证 sign 字段（SDK + 自验双保险）
3. **app_id 校验**：通知 app_id 必须 == 配置 APPID
4. **幂等**：`SELECT FOR UPDATE` + `status == "pending"` 才入账，重复回调返回 `'success'`
5. **金额二次校验**：`total_amount` 必须 == 订单金额
6. **trade_status 校验**：只接受 `TRADE_SUCCESS` / `TRADE_FINISHED`
7. **out_trade_no 存在性**：必须存在于我方订单表
8. **回调原文落库**：`notify_raw` 字段保存原始 POST 数据（审计）
9. **5 秒超时 + 必须返回 `'success'` 字符串**：否则支付宝重试 8 次

### 4.8 关键方法签名

```python
class PaymentService:
    @classmethod
    def create_topup_order(
        cls, *, tenant_id: str, account_id: str,
        amount_yuan: Decimal, client_ip: str,
        provider: str = "alipay",
    ) -> PaymentOrder: ...

    @classmethod
    def query_order(cls, *, order_id: str, requester_id: str) -> PaymentOrder: ...

    @classmethod
    def handle_alipay_notify(cls, params: dict) -> str:
        """返回 'success' 或 'fail'"""

    @classmethod
    def close_expired_orders(cls) -> int: ...

    @classmethod
    def reconcile_pending_orders(cls, *, within_hours: int = 1) -> int: ...
```

---

## 5. API 端点

所有接口位于 `/console/api`，复用 `console_ns` namespace 和现有装饰器。

### 5.1 充值订单

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| POST | `/billing/topup/orders` | owner / admin | 创建订单，body: `{provider, amount}`，返回 `{order_id, qr_code, expires_at}` |
| GET | `/billing/topup/orders/<id>` | 创建人 / owner / admin | 查订单状态（前端轮询） |
| GET | `/billing/topup/orders` | owner / admin | 订单列表，支持 `?status=&page=&limit=` |
| POST | `/billing/alipay/notify` | 公开（验签） | 支付宝异步通知，返回纯文本 `'success'` / `'fail'` |

### 5.2 工作空间钱包

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/billing/tenant/wallet` | tenant 成员 | `{balance, locked, total_topup, currency}` |
| GET | `/billing/tenant/members` | owner / admin | 成员钱包列表 + 消费汇总 |
| POST | `/billing/tenant/allocations` | owner / admin | 分配/回收，body: `{account_id, amount, description?}` |
| GET | `/billing/tenant/allocations` | owner / admin | 分配流水 |

### 5.3 个人钱包

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/billing/user/wallet` | 已登录 | `{balance, currency, is_sufficient}` |
| GET | `/billing/user/records` | 已登录 | 个人流水 `?type=deduction|allocation|rebate` |

### 5.4 超管

| Method | Path | 权限 | 说明 |
|---|---|---|---|
| GET | `/billing/admin/orders` | system_admin | 全平台订单 |
| GET | `/billing/admin/tenant-wallets` | system_admin | 全平台 tenant 钱包 |
| GET | `/billing/admin/large-topup-alerts` | system_admin | 大额充值告警列表 |
| PUT | `/billing/admin/config` | system_admin | 调整阈值（大额阈值等） |

### 5.5 错误码

| HTTP | code | 含义 |
|---|---|---|
| 400 | `INVALID_AMOUNT` | 金额非法 |
| 403 | `NOT_TENANT_ADMIN` | 非 owner/admin |
| 403 | `INSUFFICIENT_USER_BUDGET` | 个人额度不足 |
| 409 | `ALLOCATION_EXCEEDS_BALANCE` | 分配超出 tenant 可用 |
| 409 | `RECLAIM_EXCEEDS_MEMBER_BALANCE` | 回收超出成员余额 |
| 429 | `RATE_LIMITED` | 创单频率超限 |
| 500 | `PAYMENT_PROVIDER_ERROR` | 支付宝调用失败 |

---

## 6. 前端

### 6.1 文件组织

```
web/app/(commonLayout)/billing/
├── page.tsx                            # Tab：钱包 / 流水 / 订单
├── _components/
│   ├── wallet-card.tsx                 # 双余额展示
│   ├── topup-modal.tsx                 # 充值弹窗
│   ├── topup-qrcode.tsx                # 二维码 + 轮询
│   ├── allocation-table.tsx            # 成员分配表
│   ├── allocation-modal.tsx            # 分配/回收弹窗
│   ├── billing-records.tsx             # 消费流水
│   └── topup-orders.tsx                # 充值订单列表

web/app/(commonLayout)/(creator)/_components/
└── balance-banner.tsx                  # 余额不足横幅 + "去充值"
```

### 6.2 React Query Hooks

```
web/service/billing.ts          # 纯 fetch 封装
web/service/use-billing.ts      # hooks
  - useTenantWallet()
  - useUserWallet()
  - useCreateTopupOrder()
  - useTopupOrder(id)              # 自动 2s 轮询直到 paid/closed
  - useTenantMembers()
  - useAllocate()
  - useReclaim()
  - useBillingRecords({type, page})
```

### 6.3 充值组件状态机

```
pending  → 二维码 + 倒计时（"请使用支付宝扫码支付"）
paid     → ✓ "充值成功"，自动关闭，invalidate wallet 缓存
closed   → "订单已过期"，按钮"重新生成"
failed   → "支付失败"，按钮"重试"
```

### 6.4 二维码

```bash
pnpm add qrcode.react
```

```tsx
import { QRCodeSVG } from 'qrcode.react'
<QRCodeSVG value={order.qr_code} size={240} level="M" />
```

### 6.5 i18n

新增 `web/i18n/{en-US,zh-Hans}/billing.ts`，覆盖：
- topup 文案（金额、扫码提示、状态、过期、错误）
- allocation 文案（分配、回收、超分提示）
- wallet 文案（余额、可用、已分配、累计充值）

**严禁硬编码中文/英文文案**（项目规范）。

---

## 7. 定时任务

`api/schedule/payment_tasks.py`：

```python
@celery_app.task
def close_expired_payment_orders():
    """每 5 分钟：关闭过期 pending 订单"""
    PaymentService.close_expired_orders()

@celery_app.task
def reconcile_payment_orders():
    """每小时：对账，主动查 1h 内 pending 订单防丢回调"""
    PaymentService.reconcile_pending_orders(within_hours=1)
```

注册到 `api/schedule/__init__.py` Celery beat 配置。

---

## 8. 大额告警

`api/services/payment/alerts.py`：

```python
class PaymentAlertService:
    @classmethod
    def check_and_notify(cls, order: PaymentOrder) -> None:
        threshold = dify_config.ALIPAY_LARGE_AMOUNT_THRESHOLD
        if order.amount >= Decimal(threshold):
            audit_log.write(event="LARGE_TOPUP", order_id=order.id, ...)
            notify_super_admins(
                subject=f"大额充值告警 ¥{order.amount}",
                body=f"租户 {order.tenant_id} 充值 ¥{order.amount}，订单 {order.out_trade_no}",
            )
```

复用现有 `core.helper.notification` 邮件机制。**不阻塞充值流程，仅通知。**

---

## 9. 测试策略（80%+ 覆盖）

### 9.1 单元测试

```
api/tests/unit_tests/services/payment/
├── test_alipay_provider.py         # 沙箱模拟、verify_notify 正反例
├── test_payment_service.py         # 创建订单、幂等回调、入账事务
├── test_allocation_service.py      # 超分、回收过多、不变式
└── test_alerts.py                  # 大额告警触发条件
```

### 9.2 集成测试（containers）

```
api/tests/test_containers_integration_tests/services/payment/
├── test_payment_e2e.py             # 真实 DB：创单 → mock 回调 → 验账本
└── test_concurrent.py              # 并发扣费 + 并发分配的事务正确性
```

### 9.3 关键场景

1. **幂等性**：同一回调 POST 10 次，账本只入账 1 次
2. **金额篡改**：回调金额 != 订单金额 → 拒绝 + 告警
3. **签名失败**：invalid sign → 返回 `fail`，订单仍 pending
4. **分配不变式**：随机操作 1000 次后 `Σ UserBalance == TenantBalance.locked`
5. **并发扣费**：100 个并发 workflow 同时扣同一 user → 余额最终一致，不超扣
6. **过期订单**：15 分钟未支付 → status=closed
7. **个人 Tenant 自动分配**：充值 100 → owner UserBalance 自动 +100
8. **回调对账**：模拟回调丢失，定时对账主动同步状态
9. **余额耗尽拦截**：UserBalance=0 时 workflow 启动被拒绝并返回 INSUFFICIENT_USER_BUDGET

### 9.4 前端测试

```
web/__tests__/billing/
├── topup-modal.test.tsx            # 状态机、轮询、关闭
├── wallet-card.test.tsx
└── allocation-table.test.tsx
```

---

## 10. 数据迁移

新增迁移 `api/migrations/versions/<ts>_add_payment_and_tenant_balance.py`：

### 10.1 DDL

1. `CREATE TABLE tenant_balances`
2. `CREATE TABLE payment_orders`
3. `CREATE TABLE allocation_records`
4. `ALTER TABLE billing_records ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'user'`

### 10.2 数据回填

对每个现有 `UserBalance` 行：

1. 找到该 account 的"个人 Tenant"：在 `tenant_account_joins` 中查 `role=owner` 且最早创建的那个
2. 在 `tenant_balances` INSERT：
   - `tenant_id = personal_tenant_id`
   - `balance = 0`
   - `locked = user_balance.balance`（如果 ≥0；负数则置 0）
   - `total_topup = max(user_balance.balance, 0)`
3. 写一条 `allocation_records`：
   - `tenant_id`, `account_id`, `operator_id=account_id`
   - `amount = user_balance.balance`
   - `description = "数据迁移：历史余额转入"`
4. **校验**：迁移后 `Σ UserBalance == Σ TenantBalance.locked`，否则回滚

### 10.3 向后兼容

- `UserBalance` 表保留所有字段不变
- `BillingRecord.scope` 默认 `'user'`，老数据无影响
- 历史 `topup` 类型记录的 `tenant_id` 可能为空，新数据必填

---

## 11. 部署清单

### 11.1 配置

- [ ] `api/.env` 新增 12 个 ALIPAY_* 变量
- [ ] `api/.env.example` 同步更新（带注释）
- [ ] 私钥/公钥 PEM 文件挂载到 `api/secrets/alipay/`
- [ ] `.gitignore` 排除 `api/secrets/` 和 `*.pem`

### 11.2 依赖

- [ ] `api/pyproject.toml`：`uv add alipay-sdk-python`
- [ ] `web/package.json`：`pnpm add qrcode.react`

### 11.3 生产前置

- [ ] HTTPS 证书就位
- [ ] notify_url 公网可达且通过 HTTPS
- [ ] 支付宝当面付产品已开通
- [ ] Celery beat 运行中（定时任务依赖）
- [ ] 数据库迁移已执行
- [ ] 大额告警通知渠道已配置

---

## 12. 未来扩展点

1. **微信支付**：实现 `WechatProvider implements PaymentProvider`，前端 provider 选择器加 wechat 选项
2. **退款 UI**：超管发起退款 → 调支付宝 refund API → 反向出账（`balance -= refund_amount`）
3. **预付费套餐**：在 `payment_orders` 上加 `package_id` 字段，套餐到期自动转入余额
4. **企业转账**：跳过支付宝，超管直接 `topup` 大额（已有接口）
5. **消费明细导出**：CSV/Excel 下载

---

## 13. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 支付宝回调丢失 | 定时对账兜底（每小时 reconcile） |
| 回调延迟（用户已关页面） | 订单列表持久化，支付完成的订单可随时查看 |
| 沙箱与生产环境差异 | `ALIPAY_USE_SANDBOX` 切换网关，测试覆盖两个环境 |
| 私钥泄露 | PEM 文件不入库，K8s Secret 挂载，定期轮换 |
| 并发扣费超扣 | 行锁 `SELECT FOR UPDATE` + 数据库不变式 CHECK 约束 |
| 大额刷单 | 限流（5次/min/account） + 大额告警 + 审计日志 |
| 老数据迁移失败 | 迁移脚本带校验 + 事务，失败自动回滚 |

---

**设计版本**：v1.0
**评审状态**：用户已确认所有关键决策（A/B/C 选项）
