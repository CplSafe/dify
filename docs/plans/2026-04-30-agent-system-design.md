# 代理商体系设计

**日期**: 2026-04-30
**分支**: `dify-zd`
**状态**: 设计已确认,待实施

## 1. 背景与目标

### 1.1 业务背景

本系统(Dify-zd)在 2026-04-15 之前对所有 C 端用户开放了「邀请码 + 返点」功能,允许任何注册用户邀请下级并按其消费抽成。该功能的 C 端入口于 2026-04-15 整体下线(`web/app/signup/page.tsx`、创作设置弹窗中的 `invitation` / `rebate` 两个 tab 设为 `hidden:true`),后端能力(`InvitationService`、`AccountInvitation`、`RebateRecord`、`RebateConfig`、`UserBalance.rebate_pending`、Celery 结算/解冻任务)整体保留,运营层面通过 `RebateConfig.is_enabled=false` 关闭返点结算。

现产品决定将「邀请 + 返点」重构为**封闭式的代理商体系**:平台只授权特定代理商(企业或个人)发展下级,代理商通过线下签约 + 后台开通的方式获得权限,普通用户**不再具备邀请能力**。

### 1.2 目标

- **代理商身份模型**:引入 `agents` 表表达「代理商」独立身份,与 `accounts` 关联但解耦,支持后台开通、暂停、到期失效
- **代理商控制台**:代理商登录后默认进入 `/agent`,看到下级消耗大盘、下级列表、邀请页、提现页;同时保留「返回应用」切换到普通界面的能力
- **绑定流程**:代理生成长期可复用的邀请链接 / 二维码,客户(无论是否注册过)均经过显式二次确认才完成绑定
- **换绑机制**:已绑定客户可申请换绑,需后台审批;换绑前的返点归原代理(以消费时点为准)
- **返点提现**:沿用现有按消费返点的机制,新增「可提现钱包」,代理可申请提现,后台人工打款
- **后台超管页**:代理管理、换绑审批、提现审批、返点记录总览、代理消耗大盘共 5 页
- **历史数据清理**:`AccountInvitation` / `RebateRecord` 历史数据全部作废,旧的 invitation/rebate UI 组件和注册接口的 `invite_code` 入参彻底删除

### 1.3 非目标(本期不做)

多级分润、按地理自动归属、自动转账、客户自由换绑无审批、代理直接干预下级账号、客户聊天内容对代理可见、手动调整代理钱包、月度报表 PDF 导出。详见第 9 节 YAGNI 清单。

---

## 2. 数据模型

### 2.1 新增 4 张表

#### `agents`(代理商资料表)

| 字段 | 类型 | 约束 / 说明 |
|------|------|------|
| `id` | uuid | PK |
| `account_id` | uuid | FK → `accounts.id`, **UNIQUE**(一个账号最多一条代理记录) |
| `name` | varchar(128) | 签约主体名 |
| `status` | varchar(16) | `active` / `suspended`,默认 `active` |
| `rebate_rate` | numeric(5,4) NULL | 个性化返点率,为 NULL 时 fallback 到 `RebateConfig.rate` |
| `level` | varchar(16) NULL | `national` / `province` / `city`,仅展示用 |
| `region_province` | varchar(32) NULL | 仅展示用 |
| `region_city` | varchar(32) NULL | 仅展示用 |
| `contact_phone` | varchar(32) NULL | 后台联系/对账 |
| `notes` | text NULL | 后台备注(合同号、签约金额等) |
| `signed_at` | date NULL | 签约日期 |
| `expires_at` | date NULL | 授权到期日;Celery beat 每日扫描,过期自动 `suspended` |
| `created_by` | uuid | FK → `accounts.id`(开通的超管) |
| `created_at` / `updated_at` | timestamp | 标准审计字段 |

索引:`UNIQUE(account_id)`、`idx(status)`、`idx(expires_at)`(供定时任务扫描)

#### `agent_wallets`(代理钱包,与 `agents` 1:1)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | PK |
| `agent_id` | uuid | FK → `agents.id`, UNIQUE |
| `withdrawable` | numeric(12,2) | 已解冻、可提现金额(单位与 `UserBalance` 对齐,使用积分单位) |
| `total_earned` | numeric(12,2) | 累计返点(已结算合计,只增不减) |
| `total_withdrawn` | numeric(12,2) | 累计已打款合计 |
| `updated_at` | timestamp | |

设计说明:**不复用 `UserBalance.rebate_pending`**,因为代理钱包语义独立(可提现现金 vs. 平台积分余额),混表会让财务对账困难。`UserBalance.rebate_pending` 字段在迁移中**移除**(第 6 节详述)。

约束:`CHECK (withdrawable >= 0)` 数据库层兜底防止超额提现。

#### `rebind_requests`(换绑申请)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | PK |
| `account_id` | uuid | 客户账号 ID |
| `from_agent_id` | uuid | 原代理 |
| `to_agent_id` | uuid | 目标代理 |
| `status` | varchar(16) | `pending` / `approved` / `rejected` |
| `reviewer_id` | uuid NULL | 审批的超管 |
| `review_note` | text NULL | 审批备注 |
| `created_at` / `reviewed_at` | timestamp | |

约束:**部分唯一索引** `UNIQUE(account_id) WHERE status='pending'`(确保同一客户同时只有一个 pending 申请);冷静期 90 天通过应用层检查(查最近一次 `approved` 记录的 `reviewed_at`)。

#### `withdrawal_requests`(提现申请)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | uuid | PK |
| `agent_id` | uuid | FK → `agents.id` |
| `amount` | numeric(12,2) | 申请金额,≥ 100 |
| `payout_method` | varchar(16) | `alipay` / `wechat` / `bank` |
| `payout_payload` | jsonb | 按方式存储字段:支付宝(账号+姓名)、微信(微信号+姓名)、银行(开户行+卡号+姓名) |
| `status` | varchar(16) | `pending` / `paid` / `rejected` |
| `reviewer_id` | uuid NULL | |
| `review_note` | text NULL | 拒绝原因或打款流水号 |
| `created_at` / `reviewed_at` | timestamp | |

约束:**部分唯一索引** `UNIQUE(agent_id) WHERE status='pending'`(同一代理同时只能一个 pending 申请)。

### 2.2 修改的现有表

- **`account_invitations`**:`inviter_account_id` 仍指向 `accounts`(因为代理本质是 account);新增字段 `agent_id uuid NOT NULL`(指向 `agents.id`),写入时**必须**有值——这道约束在数据库层强制「只有代理身份才能产生绑定关系」
- **`rebate_records`**:新增 `agent_id uuid NOT NULL`,写入时锁定**消费时点的代理归属**;换绑后历史记录不动,新消费才生成新代理的记录
- **`user_balances`**:删除 `rebate_pending` 字段(已迁移到 `agent_wallets.withdrawable`)
- **`rebate_configs`**:保留,继续作为全局兜底费率配置

### 2.3 关系总览

```
accounts ─┬─ 1:1 ─ agents ─── 1:1 ─ agent_wallets
          │            │
          │            └─ 1:N ─ withdrawal_requests
          │
          ├─ 1:N ─ account_invitations.invitee_account_id
          │            │
          │            └─ FK ─ agents (绑定时锁定)
          │
          ├─ 1:N ─ rebind_requests (作为客户)
          │
          └─ 1:N ─ rebate_records.invitee_account_id
                       │
                       └─ FK ─ agents (消费时点锁定)
```

---

## 3. 后端架构

### 3.1 模块组织(遵循 DDD/Clean Architecture)

```
api/
├── models/agent.py                       # 新文件:Agent / AgentWallet / RebindRequest / WithdrawalRequest
├── models/creator.py                     # 改造:AccountInvitation / RebateRecord 加 agent_id;UserBalance 删 rebate_pending
├── services/
│   ├── agent/                            # 新包
│   │   ├── __init__.py
│   │   ├── agent_service.py              # 代理资料 CRUD(超管侧)
│   │   ├── agent_invitation_service.py   # 邀请码生成 + 绑定(代理侧 + 客户侧)
│   │   ├── rebind_service.py             # 换绑申请 + 审批
│   │   ├── withdrawal_service.py         # 提现申请 + 审批
│   │   ├── agent_wallet_service.py       # 钱包读写 + 待结算/已结算汇总
│   │   └── agent_dashboard_service.py    # 控制台首页聚合查询
│   └── errors/agent.py                   # AgentNotFoundError / AgentSuspendedError 等领域异常
├── controllers/console/
│   ├── agent/                            # 新包(代理商控制台 API)
│   │   ├── dashboard.py                  # GET /agent/dashboard
│   │   ├── invitees.py                   # GET /agent/invitees(下级列表)+ PATCH /agent/invitees/{id}/note
│   │   ├── invitation.py                 # POST /agent/invitations(生成邀请码)+ GET 列表
│   │   ├── withdrawal.py                 # POST /agent/withdrawals + GET 列表
│   │   └── bind.py                       # POST /agent/bind/preview + POST /agent/bind/confirm + POST /agent/bind/rebind-request
│   └── admin/agent/                      # 新包(后台超管 API)
│       ├── agents.py                     # GET/POST/PATCH /admin/agents
│       ├── rebind_review.py              # GET/POST /admin/rebind-requests
│       ├── withdrawal_review.py          # GET/POST /admin/withdrawals
│       ├── rebate_overview.py            # GET /admin/rebate-records(只读)
│       └── consumption_overview.py       # GET /admin/agent-consumption(只读大盘)
├── controllers/console/creator/
│   ├── invitation.py                     # 删除:旧的全员邀请管理接口
│   └── rebate.py                         # 删除:旧的返点账单接口
├── controllers/console/auth/
│   └── email_register.py                 # 改造:删除 invite_code 入参与 bind_invitation_on_register 调用
├── services/invitation_service.py        # 删除:整个旧 InvitationService(被 agent_invitation_service 替代)
└── schedule/
    ├── rebate_settlement_task.py         # 改造:写入 agent_wallets.withdrawable 而不是 UserBalance.rebate_pending
    ├── rebate_unfreeze_task.py           # 改造:目标改为 agent_wallets.withdrawable
    └── agent_expiry_task.py              # 新文件:每日扫描 expires_at,自动 suspend 过期代理
```

### 3.2 关键服务职责

- **`AgentService`**:`create_agent()` / `update_agent()` / `suspend_agent()` / `get_agent_by_account_id()`;创建时必须传入 `created_by`,事务内同时建 `agent_wallets` 行
- **`AgentInvitationService`**:`generate_invitation_code(agent_id)` 返回长期可复用的 code(原 `InvitationService` 是一次性,这里语义不同);`bind(account_id, code)` 在客户二次确认后调用,内含「是否已绑→走换绑申请」分支
- **`RebindService`**:`create_request()` 校验 90 天冷静期 + 唯一 pending;`approve()` 把 `account_invitations.agent_id` 切到新代理并写入 `rebound_at`(供时点判断使用);`reject()`
- **`WithdrawalService`**:`create_request()` 校验金额 ≥ 100 + ≤ wallet.withdrawable + 唯一 pending;`mark_paid()` 事务内扣 `withdrawable` + 加 `total_withdrawn` + 状态置 `paid`
- **`AgentWalletService`**:封装 `withdrawable` / `total_earned` 读写,所有 +/- 都走这一层,便于审计
- **`AgentDashboardService`**:控制台首页聚合查询,一次返回今日/7日/累计三组数据 + 钱包四个数;**注意**:消耗大盘要按下级聚合,这是 N+1 风险点,用单条 GROUP BY 查询解决

### 3.3 返点写入逻辑(本次最关键的改造)

现状:消费 → 触发 `RebateRecord.PENDING` 写入 → `UserBalance.rebate_pending +=` → 解冻任务搬到 `balance`

改造后:消费 → 触发器先 `JOIN agents ON inviter_account_id = agents.account_id AND agents.status='active'` →

- **JOIN 命中**:写 `RebateRecord(agent_id=匹配到的agent.id, status=PENDING)`,**不动** `UserBalance`
- **JOIN 未命中**(老用户的非代理 inviter,或没有 inviter):**直接跳过**,不写记录

解冻任务:`PENDING → SETTLED` 时,把金额加到 `agent_wallets.withdrawable` 和 `agent_wallets.total_earned`,而不是 `UserBalance`。

这道 JOIN 校验是「普通用户不再产生返点」的硬执行点,放在数据库写入路径而不是上游业务逻辑里,避免任何调用方绕过。

### 3.4 Celery 任务

| 任务 | 频率 | 行为 |
|------|------|------|
| `rebate_settlement_task` | 每日(沿用现有 schedule) | 改造:目标表换成 `agent_wallets`;`is_enabled=false` 时仍 no-op |
| `rebate_unfreeze_task` | 每日 | 同上 |
| `agent_expiry_task` | 每日凌晨 | 新增:扫描 `expires_at <= today AND status='active'`,批量 `suspend` |
| `rebind_cooldown_check` | 不需要定时任务 | 90 天冷静期通过 SQL 实时查询判断,无需后台维护 |

---

## 4. 前端架构

### 4.1 路由组织(沿用 Next.js App Router + 路由组模式)

现状:Dify-zd 已有 `(commonLayout)` / `(creatorLayout)` / `(humanInputLayout)` / `(shareLayout)` 四个路由组。本期新增第五个路由组 `(agentLayout)` 用于代理商控制台,与 `creatorLayout` 平级。

```
web/app/
├── (agentLayout)/                    # 新路由组 - 代理商控制台
│   ├── layout.tsx                    # 顶部导航 + "返回应用"按钮 + 代理商身份守卫
│   └── agent/
│       ├── dashboard/page.tsx        # 控制台首页(消耗大盘 + 钱包四指标)
│       ├── invitees/page.tsx         # 下级账号管理(列表 + 代理备注)
│       ├── invitation/page.tsx       # 邀请页(二维码 + 链接 + 复制按钮)
│       └── withdrawal/page.tsx       # 提现页(申请历史 + 新建申请)
├── (commonLayout)/
│   └── admin/                        # 后台超管页(沿用现有 admin 路径或扩展)
│       └── agent-management/         # 5 个超管页
├── signup/page.tsx                   # 改造:删除 invite_code 输入框 + 相关逻辑
└── components/
    ├── agent/                        # 新组件目录
    │   ├── dashboard/                # 大盘卡片、7日趋势图、下级聚合表
    │   ├── invitees/                 # 下级表 + 代理备注 inline 编辑
    │   ├── invitation/               # QRCode 组件 + 链接复制 + 海报模板(可选)
    │   ├── withdrawal/               # 申请表单(三种支付方式分支)+ 历史列表
    │   └── bind-confirm-dialog/      # 绑定/换绑二次确认弹窗
    └── creator/settings/
        ├── invitation-tab.tsx        # 删除
        └── tabs/rebate-tab.tsx       # 删除
```

### 4.2 身份感知与路由守卫

- **登录响应扩展**:`/console/api/account/profile` 在原有响应上加 `is_agent: bool` + `agent_status: 'active' | 'suspended' | null`
- **登录后跳转逻辑**(在 `app/signin/page.tsx` 或顶层 layout 中拦截):
  - `is_agent=true` 且 `agent_status='active'` → redirect 到 `/agent/dashboard`
  - `agent_status='suspended'` → redirect 到普通界面 + Toast 提示「代理身份已暂停,如有疑问联系客服」
  - 普通用户 → 走原有 redirect 逻辑(创作页 / Studio)
- **`(agentLayout)/layout.tsx` 守卫**:进入 `/agent/*` 时校验 `is_agent && agent_status==='active'`,否则 redirect 回首页(防止普通用户直接拼 URL 访问)
- **顶部「返回应用」按钮**:固定在 `agentLayout` 的导航栏,点击 redirect 到 `/apps` 或创作页;普通界面右上角用户菜单里增加「代理商控制台」入口(`is_agent=true` 才显示),点击 redirect 回 `/agent/dashboard`

### 4.3 数据获取(沿用项目现有 oRPC + TanStack Query 模式)

新增契约文件:

```
web/contract/console/
├── agent.ts                  # 代理控制台契约(/agent/* 全部端点)
├── agent-bind.ts             # 客户侧绑定契约(/agent/bind/* 端点)
└── admin-agent.ts            # 后台超管契约(/admin/agents/* 全部端点)
```

命名规则严格遵循项目现有 contract 风格(参考 `asset-library.ts`):每个 endpoint 定义 input schema、output schema、method、path,前端通过 `useQuery` / `useMutation` 消费。

### 4.4 关键 UI 组件

- **7 日趋势图**:用项目已用的图表库(`recharts` 或现有依赖,实现前确认),折线图展示按日聚合的下级消耗
- **下级聚合表**:列 = 邮箱/手机、绑定时间、最近活跃、本月消耗、累计返点贡献、代理备注;支持邮箱/备注关键字搜索
- **邀请页**:展示当前代理的邀请链接(明文 + 「复制」按钮)+ 二维码(`qrcode` npm 包前端渲染);说明文案:「客户扫码或点击链接,需注册并显式确认绑定」
- **绑定二次确认弹窗 `BindConfirmDialog`**:
  - 调 `/agent/bind/preview?code=xxx` 拿代理资料(name + level + region 等可见字段)
  - 弹窗显示「你将绑定到代理 [name](level region),绑定后该代理将获得你后续消费的返点。是否确认?」
  - 已绑定他人时,弹窗变为「你当前绑定 [X],是否申请换绑到 [Y]?需平台审核」;确认后调 `/agent/bind/rebind-request`
- **提现申请表单**:支付方式 radio 分支(支付宝 / 微信 / 银行卡),不同方式显示不同必填字段;金额输入框带「全部提取」快捷按钮 + 客户端校验(≥ 100 且 ≤ withdrawable)
- **代理备注 inline 编辑**:下级表里每行备注列点击切换成输入框,失焦或 Enter 提交,调 `PATCH /agent/invitees/{id}/note`(乐观更新)

### 4.5 国际化

全新文案放 `web/i18n/zh-Hans/agent.ts`,英文版 `web/i18n/en-US/agent.ts` 提供机翻占位(关键词如 "Agent Console"、"Withdraw"、"Rebind Request");其他语言不维护。

---

## 5. 关键流程时序

### 5.1 代理商开通(后台超管)

```
超管 → POST /admin/agents { account_id, name, rebate_rate, level, region_*, expires_at, notes }
     → AgentService.create_agent()
         ├── 校验 account_id 存在且未绑定 agent
         ├── 事务开始
         │   ├── INSERT agents(...)
         │   └── INSERT agent_wallets(agent_id, withdrawable=0, total_earned=0, total_withdrawn=0)
         └── 事务提交
     → 返回 201 + agent 资料
     → (可选)邮件通知该 account "你已被授权为代理商,请重新登录"
```

### 5.2 客户绑定流程(注册前 - 扫码场景)

```
客户扫码 → 落到 /signup?agent_code=XXX
         → 注册页只展示常规注册字段(无邀请码输入框)
         → 客户提交注册 → POST /email-register { email, password, ... } (无 invite_code 入参)
         → 注册成功 → 自动登录
         → 前端从 URL query 读取 agent_code,弹 BindConfirmDialog
         → 调 GET /agent/bind/preview?code=XXX 显示代理资料
         → 客户点 "确认绑定"
         → POST /agent/bind/confirm { code: XXX }
             → AgentInvitationService.bind(account_id, code)
                 ├── 校验 code 有效 + 代理 active
                 ├── 校验客户未绑定其他代理(若已绑 → 返回 ALREADY_BOUND,前端切换到 "换绑申请" 分支)
                 ├── 事务:INSERT account_invitations(invitee_account_id, inviter_account_id, agent_id, status='used')
                 └── 提交
         → 返回 200 + 绑定成功提示
```

### 5.3 客户绑定流程(已注册 - 扫码场景)

```
客户扫码 → 落到 /signup?agent_code=XXX(因未登录)
         → 注册页检测到已存在 session 或客户改走 /signin
         → 登录后前端发现 URL 或 sessionStorage 残留 agent_code
         → 弹 BindConfirmDialog → 同 5.2 后半段
```

实现细节:`agent_code` 在用户**未登录**时存进 sessionStorage(注册和登录两条路径都能拿到),登录/注册成功的回调里读取并触发 BindConfirmDialog。

### 5.4 换绑申请 + 审批

```
客户扫了新代理 Y 的码 → BindConfirmDialog 检测到已绑 X
                      → 弹 "申请换绑到 Y"
                      → POST /agent/bind/rebind-request { current_agent_id: X, target_agent_id: Y }
                         → RebindService.create_request()
                             ├── 校验:无 pending 申请 + 距上次 approved 已 ≥ 90 天
                             ├── INSERT rebind_requests(status='pending')
                             └── 提交
                      → Toast "换绑申请已提交,等待平台审核"

超管在后台 → GET /admin/rebind-requests?status=pending → 查看列表
           → POST /admin/rebind-requests/{id}/approve { note }
              → RebindService.approve()
                  ├── 事务:
                  │   ├── UPDATE rebind_requests SET status='approved', reviewed_at=NOW(), reviewer_id=...
                  │   └── UPDATE account_invitations SET agent_id=Y_id WHERE invitee_account_id=客户_id
                  ├── 事务提交
                  └── 触发邮件:通知 X "你的下级 [客户脱敏邮箱] 已转出";通知客户审批结果
```

**关键不变量**:`rebate_records.agent_id` 是写入时锁定的快照,不会随 `account_invitations.agent_id` 变更而迁移。所以审批通过后,X 历史的 RebateRecord 仍然属于 X(`agent_id` 仍指向 X 的 agent),不会被搬到 Y 名下。

### 5.5 返点结算 + 解冻

```
客户消费触发 RebateRecord 写入:
    SELECT a.id FROM agents a JOIN account_invitations i ON i.agent_id = a.id
    WHERE i.invitee_account_id = 消费客户_id AND a.status = 'active'
    → 命中: INSERT rebate_records(agent_id, invitee_account_id, amount, status='PENDING')
    → 未命中: 跳过(普通用户邀请的下级、suspended 代理的下级、无 inviter 的用户)

Celery beat 每日 rebate_settlement_task:
    PENDING records 满足 settlement_hour 条件 → status='SETTLED' (但仍冻结)

Celery beat 每日 rebate_unfreeze_task:
    SETTLED 且超过 freeze_days → 加到 agent_wallets.withdrawable + total_earned
                               + 更新 RebateRecord.unfrozen_at
```

### 5.6 提现申请 + 审批

```
代理 → 提现页 → 选支付方式 + 填字段 + 输金额 → POST /agent/withdrawals { amount, method, payload }
     → WithdrawalService.create_request()
         ├── 校验 amount ≥ 100 + amount ≤ wallet.withdrawable + 无 pending 申请
         ├── INSERT withdrawal_requests(status='pending')
         └── 提交(此时 withdrawable 不动,等审批通过才扣)

超管 → GET /admin/withdrawals?status=pending → 查看 + 拿到打款字段
     → 线下打款(支付宝/微信/银行)→ 拿到流水号
     → POST /admin/withdrawals/{id}/pay { transaction_id }
        → WithdrawalService.mark_paid()
            ├── 事务:
            │   ├── UPDATE withdrawal_requests SET status='paid', reviewed_at=NOW(), review_note=transaction_id
            │   ├── UPDATE agent_wallets SET withdrawable -= amount, total_withdrawn += amount
            │   └── (校验 withdrawable >= 0,否则 raise InsufficientBalanceError)
            ├── 提交
            └── 邮件通知代理 "提现已打款,请查收"
```

---

## 6. 迁移与清理方案

### 6.1 数据库迁移(单个 alembic 文件)

文件名:`api/migrations/versions/<timestamp>_add_agent_system.py`

操作顺序(必须严格按此顺序,事务内执行):

1. **建新表**:`agents` / `agent_wallets` / `rebind_requests` / `withdrawal_requests`(含所有索引和约束)
2. **加新列**:
   - `account_invitations.agent_id uuid NULL`(暂时 NULL,因为接下来要清空)
   - `rebate_records.agent_id uuid NULL`(暂时 NULL,因为接下来要清空)
3. **清空历史数据**:
   - `TRUNCATE rebate_records`
   - `TRUNCATE account_invitations`(全部失效,符合 Q-11 决策 A)
4. **改约束**:
   - `account_invitations.agent_id` 改 `NOT NULL` + 加 FK
   - `rebate_records.agent_id` 改 `NOT NULL` + 加 FK
5. **删字段**:`user_balances.rebate_pending`(已迁移到 `agent_wallets.withdrawable`,但因为历史数据已清空,不需要数据搬运)

**回滚策略**:`downgrade()` 把上述 5 步反向执行;但因为 TRUNCATE 不可逆,**回滚后历史邀请/返点数据无法恢复**。这点在 PR 描述中明确警示,且回滚前必须 DBA 备份。

### 6.2 代码清理清单

后端删除:

- `api/services/invitation_service.py` 整个文件
- `api/controllers/console/creator/invitation.py` 整个文件 + 路由注册
- `api/controllers/console/creator/rebate.py` 整个文件 + 路由注册
- `api/controllers/console/auth/email_register.py` 中 `invite_code` 入参 + `bind_invitation_on_register` 调用
- 相关测试文件:`tests/unit_tests/services/test_invitation_service.py`、`tests/unit_tests/controllers/.../test_invitation.py`、`tests/unit_tests/controllers/.../test_rebate.py`

后端改造(不删除):

- `api/schedule/rebate_settlement_task.py`:目标表 `UserBalance.rebate_pending` → `agent_wallets.withdrawable`(+ `total_earned`)
- `api/schedule/rebate_unfreeze_task.py`:同上,目标表更换
- `api/models/creator.py`:`UserBalance` 类删除 `rebate_pending` 字段;`AccountInvitation` / `RebateRecord` 加 `agent_id` 字段
- 任何消费触发返点写入的地方(grep `RebateRecord(` / `rebate_pending` 全文确认):加上「`inviter_account_id` 必须是 active agent 的 account_id」的 JOIN 校验,否则跳过写入

前端删除:

- `web/app/components/creator/settings/tabs/invitation-tab.tsx`
- `web/app/components/creator/settings/tabs/rebate-tab.tsx`
- `web/app/components/creator/settings/creator-settings-modal.tsx` 中 `invitation` / `rebate` 两个 `MENU_ITEMS` 条目
- `web/service/use-common.ts` 中 `MailRegisterPayload.invite_code` 字段
- `web/app/signup/set-password/page.tsx` 中读 URL `invite_code` 并传给 `useMailRegister` 的逻辑(改为读 `agent_code` 并存到 sessionStorage)
- 旧的 `invite_code` 相关 i18n key

前端改造:

- `web/app/signup/page.tsx`:`invite_code` query 接收逻辑改名为 `agent_code` + 透传到注册成功后的 `BindConfirmDialog` 触发逻辑(经 sessionStorage 中转)
- `web/app/signin/page.tsx`:同上,登录成功后检查 sessionStorage 是否有 `agent_code`,有则触发 BindConfirmDialog

### 6.3 配置清理

- `RebateConfig` 表保留(全局费率配置仍然有用),但运营层面建议保持 `is_enabled=true`(代理模式上线后应该启用)
- 上线后第一件事:超管在后台**确认全局 `RebateConfig.rate`**,因为新的 active agent 写入返点时会按 `agents.rebate_rate ?? RebateConfig.rate` 取值

### 6.4 上线步骤

1. 部署新代码 + 跑 alembic 迁移(此时旧 UI 已通过代码删除消失,旧 API 也已 404)
2. 超管登录后台,确认 `RebateConfig.rate` 是预期值,确认 `is_enabled=true`
3. 超管在新「代理商管理」页开通第一个代理(可以是测试账号)
4. 测试账号登录验证:进入 `/agent/dashboard` → 生成邀请链接 → 用另一个浏览器扫码注册并绑定 → 消费触发 → 验证 RebateRecord 写入
5. 全部验证通过后,正式开通生产代理

---

## 7. 安全与合规

### 7.1 权限边界

| 资源 | 普通用户 | 代理商(`agent_status=active`) | 超管(`is_system_admin`) |
|------|---------|------|------|
| 自己的账号资料 / 余额 | ✅ | ✅(沿用普通用户路径) | ✅ |
| `/agent/*` 全部端点 | ❌ 403 | ✅ 仅看/操作自己 | ❌ 403 |
| 自己的下级列表 / 备注 | N/A | ✅ 仅自己的下级 | N/A |
| 其他代理的下级 / 钱包 | ❌ | ❌ 403 | N/A(走 `/admin/*` 间接看) |
| `/admin/agents/*` 全部端点 | ❌ 403 | ❌ 403 | ✅ |
| 客户的对话内容 / app | 仅自己的 | **❌ 永远不可见** | (按现有规则) |
| 全局 `RebateConfig` | ❌ | ❌ | ✅ |

**关键不变量**:**代理商在任何路径下都不能访问下级的对话历史、application、token 明细**。代理只能看到聚合的「消费金额」和「最近活跃日期」,不下钻到具体的 LLM 输入输出。这是隐私红线。

### 7.2 接口鉴权实现

- 沿用项目现有 `@login_required` + `@account_initialization_required` + `@setup_required` 装饰器栈
- 新增 `@agent_required` 装饰器(在 `controllers/console/wraps.py` 加):查询 `agents` 表确认当前 account 是 active agent,否则 403
- 后台超管端点继续用 `_require_system_admin(current_user)` 函数式校验
- **代理商资源所有权校验**:每个 `/agent/*` 端点必须用 `agent_id = current_user.agent.id` 作为查询过滤条件,**不接受**前端传入 `agent_id`(避免 IDOR)

### 7.3 敏感数据处理

- **支付信息**:`withdrawal_requests.payout_payload` 是 jsonb,**不加密**(因为超管必须能读取去打款),但访问限制在 `_require_system_admin` 的端点;数据库层依赖现有 PostgreSQL 实例的访问控制
- **下级邮箱在代理界面的展示**:**部分脱敏**(如 `abc***@example.com`),代理只看到模糊邮箱;原始邮箱仅在审批/客服后台对超管可见
- **审计日志**:`agents` / `rebind_requests` / `withdrawal_requests` 三张表的所有变更走应用层日志(写 logger.info,带 actor + action + target),**不引入新的审计表**(YAGNI;后续真有需求再加)

### 7.4 速率限制

- `POST /agent/bind/confirm` / `/agent/bind/rebind-request`:每客户每分钟 ≤ 5 次(防止恶意批量绑定)
- `POST /agent/withdrawals`:每代理每分钟 ≤ 3 次(已经有 partial unique index,这是双保险)
- 沿用项目现有的限流中间件(参考 `email_register` 的限流模式)

### 7.5 财务安全

- **所有钱包改动必须在事务内**:返点入账、提现扣款都用 `db.session.commit()` 包住所有相关写入
- **`agent_wallets.withdrawable` CHECK 约束** `withdrawable >= 0`,数据库层兜底防止超额提现
- **提现金额上限**:`amount <= wallet.withdrawable` 在 service 层 + DB CHECK 双重校验
- **冻结期(`freeze_days`)不可绕过**:解冻任务只搬 `unfrozen_at IS NULL AND settlement_date + freeze_days <= today` 的记录;手动调用解冻的接口**不存在**(防止误操作)

---

## 8. 测试计划

### 8.1 后端测试(目标 80%+ 覆盖,遵循 TDD red-green-refactor)

**单元测试**(`api/tests/unit_tests/`):

| 模块 | 关键用例 |
|------|---------|
| `services/agent/test_agent_service.py` | 创建代理同时建钱包(事务原子性);account_id 重复 → 拒绝;create_agent 必须 created_by |
| `services/agent/test_agent_invitation_service.py` | 生成邀请码格式;suspended 代理的码 bind 拒绝;active 代理 bind 成功;已绑定客户再 bind 返回 ALREADY_BOUND |
| `services/agent/test_rebind_service.py` | 90 天冷静期(刚 89 天 vs 91 天);唯一 pending 约束(已 pending 时再申请→拒绝);approve 后 `account_invitations.agent_id` 切换;**核心**:approve 后历史 `rebate_records.agent_id` 不变 |
| `services/agent/test_withdrawal_service.py` | 金额 < 100 拒绝;金额 > withdrawable 拒绝;唯一 pending;mark_paid 事务原子性(扣钱包 + 改状态在同一事务) |
| `services/agent/test_agent_dashboard_service.py` | 单条 GROUP BY 不产生 N+1;空下级时返回零值不报错 |
| `schedule/test_rebate_settlement_task.py` | 改造后写 `agent_wallets` 而非 `UserBalance.rebate_pending`;`is_enabled=false` 时 no-op |
| `schedule/test_agent_expiry_task.py` | `expires_at <= today` 自动 suspend;active 但 expires_at NULL 不动 |

**集成测试**(CI-only,本地不跑;遵循项目规范):

- 完整绑定流程:超管开通代理 → 客户注册扫码 → 二次确认 → 客户消费 → 解冻后提现到账
- 完整换绑流程:客户绑 X → 申请换绑 Y → 超管批准 → 验证新消费归 Y、历史返点仍归 X
- 边界:suspended 代理的现有下级消费 → 不再产生新返点(JOIN 校验生效)

### 8.2 前端测试(Vitest + React Testing Library)

| 组件 / 流程 | 关键用例 |
|-------------|---------|
| `BindConfirmDialog` | 未绑定时展示「确认绑定」;已绑定时展示「申请换绑」;代理资料正确从 preview API 渲染 |
| `WithdrawalForm` | 三种支付方式切换字段联动;金额校验;「全部提取」快捷按钮 |
| `AgentDashboard` | 加载态、空数据态、四指标卡渲染、7 日折线图渲染(快照) |
| `InviteesTable` | 备注 inline 编辑乐观更新 + 失败回滚 |
| `(agentLayout)/layout.tsx` | 非代理用户访问 `/agent/*` 被 redirect |
| 登录 redirect 逻辑 | `is_agent=true` 跳 `/agent/dashboard`;`suspended` 跳普通界面 + Toast |

### 8.3 E2E(Playwright,关键路径)

1. 超管开通代理 → 代理登录 → 默认进入控制台 → 生成邀请链接 → 复制链接
2. 新用户访问邀请链接 → 注册 → 二次确认弹窗 → 确认绑定 → 控制台下级 +1
3. 已注册用户访问邀请链接 → 登录 → 弹窗 → 确认绑定
4. 代理申请提现 → 超管标记已打款 → 代理钱包扣款

### 8.4 数据迁移测试

- 用一个有历史 `account_invitations` + `rebate_records` 数据的快照库,跑 alembic upgrade,验证:
  - 两表被清空
  - `user_balances.rebate_pending` 字段被删除
  - 新表全部建立
  - 没有外键孤儿记录
- 跑 downgrade,验证表结构能回滚(数据无法恢复,在 PR 中明确说明)

---

## 9. 本期不做(YAGNI 清单)

以下功能产品已确认延后,等真有需求再加,**不要在第一版偷偷做**:

1. **多级分润 / 分销树**:省级代理拿一部分、市级代理拿一部分这种多级分润。本期是单层关系。
2. **按地理自动归属**:客户根据手机号归属地或填写省市自动归到对应省/市代理。本期省市字段只展示。
3. **自动提现转账**:对接支付宝/微信商家转账 API。本期人工打款。
4. **手动调整代理钱包**:超管直接 +/- 代理 `withdrawable`。特殊场景走工单 + DBA。
5. **审计日志独立表**:本期所有变更只走 `logger.info`,不建专门审计表。
6. **代理可干预下级**:停用账号、调整额度、查对话内容。永远不做(隐私 / 合规红线)。
7. **代理后端推送通知 / 站内信**:本期只用邮件。站内信系统单独立项。
8. **代理招募外链页面**:潜在代理填表申请的公开页面。本期纯线下签约。
9. **海报模板生成器**:邀请页生成带代理头像/二维码的精美海报图片。本期只给链接 + 二维码。
10. **客户自由换绑无审批**:本期所有换绑都走后台审批。
11. **月度返点报表 PDF 导出**:本期只支持 CSV 导出(且只在后台超管的两个报表页)。
12. **代理多账号绑定**:一个代理身份可关联多个 account。本期严格 1:1。
