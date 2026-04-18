# Dify 前端 P1 实施计划：社交账号管理

**日期**: 2026-04-18
**关联设计**: [2026-04-18-social-auto-upload-design.md](./2026-04-18-social-auto-upload-design.md)
**阶段范围**: P1（仅"账号管理"，平台仅 douyin；发布抽屉留到 P2）
**状态**: 计划已定稿，待实施

---

## Overview

在 Dify Web 创作中心新增"社交账号管理"页面，对接后端 P1 提供的账号 CRUD 与扫码授权 API。本期只支持抖音平台，提供账号列表展示、添加账号扫码弹窗（含轮询状态机与倒计时）、删除账号。所有用户文案使用 i18n。

## Requirements

- 路由：`/creator/social-publish/accounts`，挂在 `creatorLayout` 下，未登录会被现有 `AppInitializer` 拦截。
- 页面：账号列表 + 添加账号入口 + 空状态。
- 仅抖音（`platform === 'douyin'`），UI 上其它平台 tab 禁用并标"即将上线"。
- 扫码二维码 base64 直接 `<img src="data:image/png;base64,..."/>` 渲染，倒计时 03:00。
- 状态机覆盖：`waiting → scanned → success | expired | failed`，过期允许刷新。
- 轮询策略：每 2s 一次 `GET /auth/status/{session_id}`，3 分钟（最多 90 次）后停。
- 严格 TypeScript：禁止 `any`，所有公共 API/Props 显式类型；ESLint + tsgo 必须过。
- 复用 `web/app/components/base/ui/dialog`、`base/ui/toast`、`base/button` 等基础组件；遵守 overlay 迁移规则（仅用 `base/ui/*`）。
- i18n 双语 zh-Hans + en-US，禁止硬编码用户可见文案。
- 强隔离信任后端：前端只透传 `current_tenant_id`（由 axios base 自动带 cookie/JWT），不做客户端校验。

---

## A. 路由结构

P1 文件清单（全部新增）：

```
web/app/(creatorLayout)/creator/social-publish/
├── layout.tsx                     # 仅做命名空间 i18n provider，可选
├── page.tsx                       # 重定向到 /accounts（或直接渲染列表）
└── accounts/
    └── page.tsx                   # P1 入口页面：标题区 + <SocialAccountsView />

web/app/components/creator/social-publish/
├── accounts-view.tsx              # 页面主容器（拉数据 + 列表 + 添加按钮）
├── social-account-list.tsx        # 按平台分组显示
├── social-account-card.tsx        # 单卡片（昵称/头像/状态/操作）
├── social-account-empty.tsx       # 空状态 + CTA
├── add-account-modal.tsx          # 选平台 → 二维码 → 状态机
├── platform-picker.tsx            # 抖音 / 小红书(disabled) / 快手(disabled)
├── qr-code-display.tsx            # 二维码 + 倒计时 + 状态文案
├── account-status-badge.tsx       # active / expired / pending_auth 徽标
└── constants.ts                   # 平台元数据（label/icon/color/enabled）

web/service/social-publish.ts      # API 调用层
web/hooks/use-social-accounts.ts   # SWR 列表 hook
web/hooks/use-auth-session.ts      # 扫码会话 + 轮询 hook
web/i18n/zh-Hans/social-publish.json
web/i18n/en-US/social-publish.json
```

i18n 命名空间需要在 `web/i18n-config/resources.ts` 注册（新增 `socialPublish` key + 进入 `namespaces` 数组），并跑一次类型生成脚本。

> 侧边栏 `web/app/components/creator/sidebar.tsx` 同期增加一个"社交账号"导航项指向新路由（用 `RiUserShared2Line`），但不破坏现有"发布作品"导航。

---

## B. 组件树

```
<CreatorSocialPublishAccountsPage />               page.tsx，server component shell
└── <SocialAccountsView />                          'use client'
    ├── PageHeader（h1 + 描述 + [+ 添加账号] Button）
    ├── <SocialAccountList accounts={...} />
    │   ├── 平台 group: <PlatformGroupHeader platform="douyin" count={n} />
    │   └── <SocialAccountCard
    │            account={...}
    │            onDelete={...}
    │            onReauth={...} />  × N
    ├── <SocialAccountEmpty onAdd={...} />（accounts 为空时显示）
    └── <AddAccountModal
              open={...}
              onOpenChange={...}
              onSuccess={...} />
        ├── Step 1: <PlatformPicker selected onSelect />
        └── Step 2: <QrCodeDisplay
                       qrBase64={...}
                       expiresAt={...}
                       status={...}
                       onRefresh={...}
                       onRetry={...} />
```

### 关键 Props / State

#### `SocialAccountsView`
- 不接 props
- 内部：`useSocialAccounts()` 拿列表与刷新；`useState<boolean>` 控制 modal 开关
- 关键交互：`onSuccess` 回调里 `mutate()` 刷新列表 + toast.success

#### `SocialAccountList`
```ts
interface SocialAccountListProps {
  accounts: SocialAccount[]
  onDelete: (id: string) => Promise<void>
  onReauth: (account: SocialAccount) => void
}
```
- 内部按 `platform` group by；P1 只会有 `douyin` 一组
- 用 `aria-label` 标注分组

#### `SocialAccountCard`
```ts
interface SocialAccountCardProps {
  account: SocialAccount
  onDelete: (id: string) => Promise<void>
  onReauth: (account: SocialAccount) => void
}
```
- State：`isDeleting: boolean`
- 删除走 `AlertDialog` 二次确认（用 `base/ui/alert-dialog`）
- 状态徽标：`active`（绿）/ `expired`（黄+"重新授权"按钮）/ `pending_auth`（灰）
- 头像懒加载，错误时用文字首字符占位

#### `AddAccountModal`
```ts
interface AddAccountModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: (account: SocialAccountSummary) => void
}
```
- State：
  - `step: 'platform' | 'qrcode'`
  - `platform: SocialPlatform | null`
  - 通过 `useAuthSession()` 拿到 `session`、`status`、`error`、`startSession`、`refresh`、`reset`
- 关闭时（`open === false`）必须 `reset()` 停止轮询 + 清状态
- `success` 后停留 3 秒展示 ✅，自动关闭并触发 `onSuccess`

#### `QrCodeDisplay`
```ts
interface QrCodeDisplayProps {
  qrBase64: string
  expiresAt: number               // ms 时间戳
  status: AuthSessionStatus
  errorMessage?: string
  account?: SocialAccountSummary  // success 时显示昵称头像
  onRefresh: () => void
  onRetry: () => void
}
```
- 内部 `useCountdown(expiresAt)` 复用 `topup-modal.tsx` 同名 hook（抽到 `web/hooks/use-countdown.ts`）
- `status='waiting'` 显示二维码 + "请使用抖音 App 扫码"
- `status='scanned'` 二维码半透明 + spinner + "已扫码，请在手机上确认"
- `status='success'` 替换为头像 + 昵称 + ✅
- `status='expired'` 二维码灰显 + 文案 + [刷新]
- `status='failed'` 错误图标 + errorMessage + [重试]

---

## C. API service 函数签名

文件：`web/service/social-publish.ts`，沿用 `service/creator-task.ts` 风格（`get/post/del`，导出强类型函数）。

```ts
import { del, get, post } from '@/service/base'

export type SocialPlatform = 'douyin' | 'xhs' | 'ks'

export type SocialAccountStatus = 'active' | 'expired' | 'pending_auth'

export type SocialAccount = {
  id: string
  platform: SocialPlatform
  display_name: string | null
  avatar_url: string | null
  status: SocialAccountStatus
  last_check_at: string | null   // ISO8601
  created_at: string
}

export type SocialAccountSummary = Pick<
  SocialAccount,
  'id' | 'display_name' | 'avatar_url'
>

export type AuthSessionStatus
  = | 'waiting'
    | 'scanned'
    | 'success'
    | 'expired'
    | 'failed'

export type StartAuthSessionPayload = {
  platform: SocialPlatform
}

export type StartAuthSessionResponse = {
  session_id: string
  qr_image_base64: string  // 不带 data: 前缀
  expires_in: number       // 秒，预期 180
}

export type AuthSessionStatusResponse = {
  status: AuthSessionStatus
  account?: SocialAccountSummary
  message?: string
}

const BASE = '/social-publish/accounts'

export const listSocialAccounts = (): Promise<{ accounts: SocialAccount[] }> =>
  get<{ accounts: SocialAccount[] }>(BASE)

export const deleteSocialAccount = (id: string): Promise<void> =>
  del(`${BASE}/${id}`)

export const startAuthSession = (
  payload: StartAuthSessionPayload,
): Promise<StartAuthSessionResponse> =>
  post<StartAuthSessionResponse>(`${BASE}/auth/start`, { body: payload })

export const fetchAuthSessionStatus = (
  sessionId: string,
): Promise<AuthSessionStatusResponse> =>
  get<AuthSessionStatusResponse>(`${BASE}/auth/status/${sessionId}`)
```

约定：
- 后端契约见设计文档第 4.1 节。
- 不要在 service 内做"包装 try/catch 吞错"；交给 hook 层统一处理。
- 任何接口出错都让 `service/base` 抛 `Error`（含 status），由 hook/组件 toast 显示。

---

## D. SWR hook 设计

### `useSocialAccounts`

文件：`web/hooks/use-social-accounts.ts`

```ts
import useSWR from 'swr'
import { listSocialAccounts, type SocialAccount } from '@/service/social-publish'

export type UseSocialAccountsResult = {
  accounts: SocialAccount[]
  isLoading: boolean
  error: Error | null
  mutate: () => Promise<void>
}

const KEY = '/social-publish/accounts'

export function useSocialAccounts(): UseSocialAccountsResult {
  const { data, error, isLoading, mutate } = useSWR(
    KEY,
    () => listSocialAccounts(),
    {
      revalidateOnFocus: true,        // 切回页面立刻刷状态（cookie 可能已过期）
      revalidateOnReconnect: true,
      dedupingInterval: 5_000,
      shouldRetryOnError: false,      // 接口错误一次性 toast
    },
  )

  return {
    accounts: data?.accounts ?? [],
    isLoading,
    error: error instanceof Error ? error : null,
    mutate: async () => { await mutate() },
  }
}
```

错误处理约定：
- `error !== null` 时页面顶部红色 banner 显示"加载失败，[重试]"，重试按钮调 `mutate()`。
- 删除/添加完成后由调用方 `await mutate()`，不靠 SWR 自动 revalidate。

### `useAuthSession`

文件：`web/hooks/use-auth-session.ts`，自管轮询，**不**用 SWR（轮询语义不对路）。

```ts
export type UseAuthSessionState =
  | { kind: 'idle' }
  | { kind: 'starting' }
  | {
      kind: 'active'
      sessionId: string
      qrBase64: string
      expiresAt: number
      status: AuthSessionStatus
      account?: SocialAccountSummary
      errorMessage?: string
    }
  | { kind: 'error'; message: string }

export type UseAuthSessionResult = {
  state: UseAuthSessionState
  start: (platform: SocialPlatform) => Promise<void>
  refresh: () => Promise<void>   // 过期后重新申请二维码
  reset: () => void              // 关闭弹窗时调用
}
```

要点：
- 内部 `setInterval(2000)` 驱动 `fetchAuthSessionStatus`；进入终止态（`success | expired | failed`）后立刻 `clearInterval`。
- 同时持有一个 `setTimeout(180_000)` 守护：到点强制把状态切到 `expired` 并停止轮询。
- 网络错误：连续失败 ≥ 3 次进入 `error` 态；单次失败仅日志（不打扰用户）。
- 卸载/`reset()` 时一定 `clearInterval` + `clearTimeout`，所有 ref 复位。
- 时间统一用 `Date.now()` 比对，不依赖服务端时钟。

---

## E. AddAccountModal 状态机

```
                    ┌──────────────┐
   open=false ────►│   closed     │
                    └──────┬───────┘
                           │ open=true
                           ▼
                    ┌──────────────┐
                    │  pickPlatform │
                    └──────┬───────┘
                           │ user selects 'douyin'
                           │ → call start('douyin')
                           ▼
                    ┌──────────────┐
                    │   starting   │  (loading spinner)
                    └──────┬───────┘
                           │
              start success│         start failure
              ┌────────────┴────────────────┐
              ▼                             ▼
      ┌──────────────┐             ┌──────────────┐
      │   waiting    │ ◄──refresh──┤    failed    │
      └──────┬───────┘             └──────────────┘
             │ poll: status='scanned'
             ▼
      ┌──────────────┐
      │   scanned    │
      └──────┬───────┘
             │ poll: status='success'
             ▼
      ┌──────────────┐
      │   success    │ ─── 3s 自动关闭 + onSuccess(account)
      └──────────────┘

      其它两条死路：
       waiting/scanned ── poll status='expired' 或 180s 超时 ──► expired
                                                             └─[refresh]→ starting
       waiting/scanned ── poll status='failed' 或 3 次网络错 ──► failed
                                                             └─[retry]→ starting
       任一状态 ── close ──► closed（同时 reset() 停轮询）
```

转换表：

| 当前态 | 触发 | 下一态 | 副作用 |
|---|---|---|---|
| closed | open + 选 douyin | starting | `start('douyin')` |
| starting | resp 200 | waiting | 启动 2s 轮询 + 180s 守护 |
| starting | resp error | failed | toast.error |
| waiting | poll=scanned | scanned | 二维码半透明 |
| waiting | poll=success | success | 停止轮询，3s 后 `onSuccess` + close |
| waiting | poll=expired \| 180s 到 | expired | 停止轮询 |
| scanned | poll=success | success | 同上 |
| scanned | poll=expired | expired | 同上 |
| 任一非 closed | 用户关闭 | closed | `reset()`：清 timer/state |
| expired | 点击"刷新" | starting | 复用同一 platform |
| failed | 点击"重试" | starting | 复用同一 platform |

---

## F. 二维码轮询策略

| 项 | 值 / 行为 |
|---|---|
| 轮询接口 | `GET /console/api/social-publish/accounts/auth/status/{session_id}` |
| 轮询间隔 | 2000 ms |
| 总时长上限 | 180_000 ms（3 分钟），到时强制 `expired` |
| 最多请求次数 | ≤ 90（180 / 2） |
| 终止态 | `success` / `expired` / `failed` 立即 stop |
| 网络失败 | 连续 < 3 次：忽略+继续；连续 ≥ 3 次：进入 `failed`，提示"网络异常请重试" |
| 后台标签页 | `document.visibilityState !== 'visible'` 时仍继续（轻量请求，不必暂停），但回到前台立即触发一次 |
| 关闭弹窗 | 立刻 `clearInterval` + `clearTimeout` + state 复位，不等响应 |
| 过期允许刷新 | `expired` 状态显示 [刷新] 按钮 → `start(platform)` 再走一遍状态机；用户连点不重叠（`starting` 时禁用） |
| 抖动防护 | 同一 sessionId 不会被重复 `start`；新 `start` 前先 `reset()` |

---

## G. i18n key 列表（中英对照）

文件：`web/i18n/zh-Hans/social-publish.json` 与 `web/i18n/en-US/social-publish.json`，命名空间 `socialPublish`。

| key | zh-Hans | en-US |
|---|---|---|
| `page.title` | 社交账号管理 | Social Accounts |
| `page.subtitle` | 绑定抖音 / 小红书 / 快手账号，发布作品时一键直发。 | Bind your Douyin / Xiaohongshu / Kuaishou accounts to publish in one click. |
| `page.addAccount` | 添加账号 | Add account |
| `empty.title` | 还没有绑定账号 | No accounts yet |
| `empty.desc` | 添加你的第一个抖音账号，开始一键发布。 | Add your first Douyin account to start publishing. |
| `empty.cta` | 添加抖音账号 | Add Douyin account |
| `platform.douyin` | 抖音 | Douyin |
| `platform.xhs` | 小红书 | Xiaohongshu |
| `platform.ks` | 快手 | Kuaishou |
| `platform.comingSoon` | 即将上线 | Coming soon |
| `status.active` | 已授权 | Active |
| `status.expired` | 授权已过期 | Expired |
| `status.pending_auth` | 等待授权 | Pending |
| `status.lastCheck` | 上次校验 {{time}} | Last checked {{time}} |
| `card.reauth` | 重新授权 | Re-authorize |
| `card.delete` | 删除 | Remove |
| `card.deleteConfirm.title` | 确认删除该账号？ | Remove this account? |
| `card.deleteConfirm.desc` | 删除后将无法发布到该账号，已发布的作品不受影响。 | After removal you can't publish to this account. Already-published posts are unaffected. |
| `card.deleteConfirm.cancel` | 取消 | Cancel |
| `card.deleteConfirm.confirm` | 删除 | Remove |
| `addModal.title` | 添加账号 | Add account |
| `addModal.pickPlatform` | 选择平台 | Choose a platform |
| `addModal.starting` | 正在生成二维码… | Generating QR code… |
| `addModal.scanTip` | 请使用抖音 App 扫码 | Scan with the Douyin app |
| `addModal.scannedTip` | 已扫码，请在手机上确认 | Scanned. Please confirm on your phone. |
| `addModal.successTitle` | 绑定成功 | Connected |
| `addModal.successDesc` | 已绑定 {{name}} | Connected as {{name}} |
| `addModal.expiredTitle` | 二维码已过期 | QR code expired |
| `addModal.expiredDesc` | 请点击刷新重新生成 | Click refresh to generate a new one |
| `addModal.refresh` | 刷新二维码 | Refresh |
| `addModal.failedTitle` | 授权失败 | Authorization failed |
| `addModal.retry` | 重试 | Retry |
| `addModal.countdown` | 剩余 {{time}} | {{time}} left |
| `addModal.networkError` | 网络异常，请检查后重试 | Network error, please retry |
| `toast.deleteSuccess` | 已删除账号 | Account removed |
| `toast.deleteFailed` | 删除失败：{{message}} | Remove failed: {{message}} |
| `toast.addSuccess` | 已添加账号 {{name}} | Added {{name}} |
| `toast.startFailed` | 生成二维码失败：{{message}} | Failed to start auth: {{message}} |
| `error.loadFailed` | 加载账号列表失败 | Failed to load accounts |
| `error.retry` | 重试 | Retry |

注册：
1. `web/i18n-config/resources.ts` 新增 `import type socialPublish from '../i18n/en-US/social-publish.json'`，加入 `Resources` 与 `namespaces`。
2. 调用侧用 `const { t } = useTranslation('socialPublish')`。

---

## H. UI Mockup（参考设计文档 7.2）

### 页面（accounts/page.tsx）

```
┌──────────────────────────────────────────────────────────────┐
│  社交账号管理                              [+ 添加账号]      │
│  绑定抖音 / 小红书 / 快手账号，发布作品时一键直发。           │
├──────────────────────────────────────────────────────────────┤
│  抖音 (2)                                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ (头像) 抖小妹                ● 已授权              ⋯  │ │
│  │        上次校验 1 小时前                              │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ (头像) 抖大哥                ▲ 授权已过期 [重新授权] │ │
│  │        上次校验 3 天前                                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  小红书（即将上线）  快手（即将上线）                         │
└──────────────────────────────────────────────────────────────┘
```

### 空状态

```
┌──────────────────────────────────────────────────────────────┐
│             ┌──────────┐                                     │
│             │   📱     │                                     │
│             └──────────┘                                     │
│         还没有绑定账号                                        │
│  添加你的第一个抖音账号，开始一键发布。                       │
│              [+ 添加抖音账号]                                │
└──────────────────────────────────────────────────────────────┘
```

### Add Modal — pickPlatform

```
┌──────── 添加账号 ────────────────────×─┐
│  选择平台                              │
│  ┌──────────┐ ┌──────────┐ ┌────────┐ │
│  │  抖音 ✓  │ │ 小红书   │ │ 快手   │ │
│  │          │ │ 即将上线 │ │ 即将上线│ │
│  └──────────┘ └──────────┘ └────────┘ │
│                                        │
│                       [取消]  [下一步] │
└────────────────────────────────────────┘
```

### Add Modal — qrcode (waiting)

```
┌──────── 添加抖音账号 ────────────×─┐
│         ┌────────────────┐         │
│         │                │         │
│         │   QR CODE      │         │
│         │   (base64 img) │         │
│         │                │         │
│         └────────────────┘         │
│   请使用抖音 App 扫码              │
│   剩余 02:47                       │
│                                    │
│        ⟳ 等待扫码中…              │
└────────────────────────────────────┘
```

### Add Modal — scanned

```
│        [QR 半透明]                 │
│        ✓ 已扫码                    │
│   请在手机上确认                   │
```

### Add Modal — success

```
│         (头像)                     │
│         抖小妹                     │
│         ✓ 绑定成功                 │
│         3 秒后自动关闭…            │
```

### Add Modal — expired / failed

```
│        [QR 灰显]                   │
│        二维码已过期                │
│        [刷新二维码]                │
```

---

## I. 现有组件复用清单

| 复用 | 路径 | 用途 |
|---|---|---|
| `Button` | `@/app/components/base/button` | 主按钮、次按钮 |
| `Dialog`, `DialogContent` | `@/app/components/base/ui/dialog` | AddAccountModal 容器 |
| `AlertDialog` | `@/app/components/base/ui/alert-dialog` | 删除二次确认 |
| `toast` | `@/app/components/base/ui/toast` | 成功/失败提示 |
| `Tooltip` | `@/app/components/base/ui/tooltip` | 状态徽标 hover 解释 |
| `cn` | `@/utils/classnames` | 条件 class |
| `useTranslation` | `react-i18next` | 文案 |
| `useCountdown` | 抽自 `topup-modal.tsx` 到 `@/hooks/use-countdown.ts` | 倒计时 |
| `service/base` 的 `get/post/del` | `@/service/base` | HTTP 调用 |
| `RemixIcon` 图标 | `@remixicon/react` | `RiUserShared2Line`、`RiCheckboxCircleFill`、`RiAlertFill`、`RiRefreshLine` 等 |

> overlay 规则：禁止从 `@/app/components/base/modal` 等 legacy 路径引入。

---

## J. 测试清单

### J.1 单元测试（Jest + RTL）

按 `web/CLAUDE.md` 与 `frontend-testing` skill 要求落到组件同级 `__tests__/` 目录。

- `service/social-publish.spec.ts`
  - `listSocialAccounts` 透传 GET 路径
  - `startAuthSession` body 正确
  - `fetchAuthSessionStatus(sessionId)` URL 拼接正确
  - `deleteSocialAccount` DELETE 路径正确
- `hooks/use-social-accounts.spec.ts`
  - 默认返回空数组
  - mutate 触发新一次 fetch
  - 错误时 `error !== null`
- `hooks/use-auth-session.spec.tsx`（fake timers）
  - 启动 → waiting 后每 2s 调用一次 status
  - status=scanned 不停轮询
  - status=success 停止轮询
  - 180s 到点强制 expired
  - reset() 清 timer
  - 连续 3 次网络错进入 failed
- `components/add-account-modal.spec.tsx`
  - 初始展示 platform picker
  - 选 douyin 调用 start
  - waiting → scanned 文案切换
  - success 3s 后调 onSuccess + onOpenChange(false)
  - expired 时 [刷新] 触发新一次 start
  - 关闭弹窗调 reset()
- `components/qr-code-display.spec.tsx`
  - 渲染 base64 img
  - 倒计时格式 `mm:ss`
  - 各 status 文案
- `components/social-account-card.spec.tsx`
  - active / expired / pending_auth 三态渲染差异
  - 删除点击 → AlertDialog → 确认调用 onDelete
- `components/social-account-list.spec.tsx`
  - 按 platform 分组
  - 空数组渲染 SocialAccountEmpty

### J.2 E2E（Playwright）

- `e2e/social-publish-accounts.spec.ts`：登录 → 进入 `/creator/social-publish/accounts` → 看到空状态 → 点添加 → 选抖音 → mock 后端返回二维码 → mock status 序列 `waiting × 1, scanned × 1, success` → 弹窗关闭 → 列表出现一条新账号。
- `e2e/social-publish-accounts-expired.spec.ts`：mock status 序列 `waiting × 5, expired` → 看到过期 UI → 点刷新 → 拿到新 sessionId 继续。
- `e2e/social-publish-accounts-delete.spec.ts`：列表已有一条 → 删除 → toast → 列表为空。

### J.3 覆盖率

- 目标 ≥ 80%。`useAuthSession` 与 `AddAccountModal` 是关键路径，要求行覆盖 ≥ 90%。

---

## K. 工作量估算（细化到小时，单人）

| 任务 | 估算 (h) |
|---|---|
| **A. 脚手架与 i18n 注册** | 3 |
| 路由文件 + 命名空间注册 + 资源类型生成 | 3 |
| **B. service & hooks** | 8 |
| `service/social-publish.ts` + 单测 | 2 |
| `useSocialAccounts` + 单测 | 2 |
| `useAuthSession`（含 fake-timer 单测） | 4 |
| **C. 列表 & 卡片组件** | 8 |
| `SocialAccountList` + `SocialAccountCard` + `Empty` | 5 |
| 三种状态徽标 + 删除确认 + 单测 | 3 |
| **D. AddAccountModal & QrCodeDisplay** | 12 |
| Modal 状态机 + Step 切换 | 4 |
| `QrCodeDisplay`（倒计时、4 种状态 UI） | 4 |
| 联调 + 单测 | 4 |
| **E. 页面装配 + 侧边栏入口** | 4 |
| `accounts/page.tsx` + sidebar 加链接 | 2 |
| 顶部 banner / loading / error 处理 | 2 |
| **F. i18n 中英文案** | 3 |
| zh-Hans + en-US 落地 + 校对 | 3 |
| **G. E2E 三条用例** | 6 |
| Playwright mock + 三条 spec | 6 |
| **H. ESLint / tsgo / lint 修复** | 2 |
| **I. Code review + 缓冲** | 4 |
| **合计** | **50 小时 ≈ 6.25 人日** |

风险缓冲后取 **6–7 人日**。与设计文档 P1 总预算（4-6d 后端 + 前端共担）一致，不阻塞 P2。

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 后端 P1 接口字段变动 | service 层窄接口、TypedDict 风格 union；接口冒烟用 mock 提前对齐 |
| 轮询泄漏导致内存/请求堆积 | hook 内部唯一 timer ref；`reset()` 必清；卸载时清 |
| 二维码 base64 过大导致重渲染抖动 | `<img>` 加 `key={sessionId}`，避免 src 变化触发 layout shift；外层固定 200×200 |
| 多次连续点 [刷新] | `state.kind === 'starting'` 时 [刷新] 按钮 disabled |
| i18n 漏翻 | tsgo 校验 + lint：所有 `t('socialPublish.xxx')` 必须在两个 json 都存在 |
| overlay 规则违规 | 评审清单确认仅引用 `base/ui/*` |
| 关闭抽屉时忘记终止后端会话 | 设计上后端会话有 180s TTL，前端无须显式关闭；只在文档记录此约定 |

---

## Success Criteria

- [ ] 路由 `/creator/social-publish/accounts` 可访问且鉴权生效
- [ ] 空状态、含数据状态、加载失败状态都有 UI
- [ ] 添加账号扫码全链路打通（waiting → scanned → success）并刷新列表
- [ ] 二维码倒计时准确，到时自动 expired
- [ ] expired 可刷新；failed 可重试
- [ ] 删除账号有二次确认，成功后列表实时更新
- [ ] 中英文案完整，无硬编码
- [ ] `pnpm lint:fix` 通过；`pnpm type-check:tsgo` 通过；`pnpm build` 通过
- [ ] 单元测试覆盖率 ≥ 80%（关键路径 ≥ 90%）
- [ ] 三条 E2E 通过
- [ ] 隔离测试：用 A 用户的 session 调 B 的 account_id 走 DELETE 应返回 404/403（前端只验证 UI 层不出现跨租户数据）

---

## 附录：与 P2 的衔接

- `service/social-publish.ts` 增加 task 相关函数（`createPublishTask`、`listPublishTasks`、`retryTask`、`cancelTask`）。
- `useSocialAccounts` 在 P2 复用，作为发布抽屉的"账号选择器"数据源；额外加 `accountsByPlatform` 派生选择器即可。
- `AuthSessionStatus` 与 `SocialAccount` 类型均设计为 `xhs/ks` 友好（已是 union），新增平台只需放开 `platform-picker` 的 `disabled`。
- `awaiting_reauth` 自动恢复 toast 在 P3 接入；P1 不做。
