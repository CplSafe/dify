# 发布中心：抖音 / 小红书 / 快手 自动发布设计

**日期**: 2026-04-18
**作者**: 头脑风暴产出（用户 weiyi01191@gmail.com + Claude）
**状态**: 设计已确认，准备进入实施

---

## 1. 背景与目标

### 1.1 业务诉求

- 项目"创作中心"已能产出视频作品（`creator_work` 表存视频/图片）
- 用户希望在发布中心**一键把作品发布到抖音 / 小红书 / 快手**
- 每个用户（tenant）可能绑定多个平台账号（如多个抖音号）
- **强隔离**：A 用户绝不能看到、调用 B 用户的账号
- 仅"添加账号"需扫码，发布过程全程**无头**

### 1.2 复用方案

引入开源项目 [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload)（10k+ stars）：

- 已实现抖音 / 小红书 / 快手 / 视频号 / 哔哩哔哩等多平台 Playwright 上传
- 已有 `cookie_auth(account_file)` 校验登录态
- 已有 `/login` SSE 推送二维码
- 自带 `sau_backend.py` Flask 路由 + SQLite 账号表

**复用策略**：fork 后独立 git、独立部署、独立进程；不嵌入 Dify api。

---

## 2. 整体架构

```
┌─────────────────────┐         ┌─────────────────────┐
│  Dify Web (Next)    │         │  Dify API (Flask)   │
│  发布中心 UI        │ ←HTTP→ │  publish 模块       │
│  - 账号列表         │         │  - 鉴权/隔离        │
│  - 二维码弹窗       │         │  - 入队/优先级      │
│  - 发布历史         │         │  - 等级判定         │
└─────────────────────┘         └──────────┬──────────┘
                                           │ HTTP (X-Sau-Token)
                                           ▼
                                ┌─────────────────────┐
                                │  sau-api            │
                                │  (FastAPI)          │
                                │  独立容器 :8001     │
                                │  - /accounts/check  │
                                │  - /login (SSE QR)  │
                                │  - /postVideo       │
                                │  - /poi/search      │
                                │  - /collections     │
                                └─────────────────────┘
                                           ▲
                                ┌──────────┴──────────┐
                                │  sau-worker (N)     │
                                │  Celery 消费 publish 队列 │
                                │  Playwright (patchright) │
                                └─────────────────────┘

数据层：
  Dify Postgres   social_publish_account / social_publish_task
  sau SQLite      原生 account 表（cookie 文件路径、状态）
  sau filesystem  cookies/{tenant_id}/{platform}/{acct}.json (0600)
  Redis broker    Celery + 信号量（限并发）

部署：
  - sau 项目独立 git fork，独立 Docker 容器（sau-api + sau-worker 两个）
  - 共享 Dify 现有 Redis broker
  - 不共享数据库
```

### 2.1 进程拆分

sau 内部拆 **2 个进程**：

| 进程 | 角色 | 关键依赖 |
|---|---|---|
| `sau-api` (FastAPI) | 接 Dify 调用：账号 check、登录 SSE、入队、查询 | sau 原生路由 + 共享 Redis |
| `sau-worker` (Celery) | 消费 `publish_*` 队列，跑 Playwright 上传 | patchright (Playwright fork) |

同一个 repo，docker-compose 起两个容器。

### 2.2 鉴权（Dify ↔ sau）

- sau 服务监听**内网**，`SAU_INTERNAL_TOKEN` 共享密钥
- 所有 Dify → sau 请求 header `X-Sau-Token: <token>`
- sau 接收 `tenant_id` 仅记日志，**不做权限校验**（信任主项目）
- **隔离的唯一防线在 Dify API 层**：`account.tenant_id == current_tenant_id`

---

## 3. 数据模型

### 3.1 Dify 主库新增 2 张表

```sql
-- 社交账号映射表（隔离主人 = tenant_id）
CREATE TABLE social_publish_account (
  id              UUID PRIMARY KEY,
  tenant_id       UUID NOT NULL,           -- 隔离主键
  platform        VARCHAR(16) NOT NULL,    -- douyin / xhs / ks
  sau_account_id  VARCHAR(64) NOT NULL,    -- sau 内部 id
  display_name    VARCHAR(64),             -- 抖音昵称等
  avatar_url      TEXT,
  status          VARCHAR(16) NOT NULL,    -- active / expired / pending_auth
  last_check_at   TIMESTAMPTZ,
  created_by      UUID NOT NULL,           -- account.id（操作人，仅审计）
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_spa_tenant_platform ON social_publish_account(tenant_id, platform);
CREATE UNIQUE INDEX uk_spa_sau_account ON social_publish_account(sau_account_id);

-- 发布任务表
CREATE TABLE social_publish_task (
  id                UUID PRIMARY KEY,
  tenant_id         UUID NOT NULL,           -- 隔离主键
  account_id        UUID NOT NULL,           -- → social_publish_account.id
  platform          VARCHAR(16) NOT NULL,
  work_id           UUID,                    -- → creator_work.id（来源作品）
  video_url         TEXT NOT NULL,           -- OSS 预签名 URL 或本地路径
  cover_url         TEXT,
  title             VARCHAR(255) NOT NULL,
  description       TEXT,
  tags              JSONB,                   -- ["xx","yy"]
  platform_payload  JSONB,                   -- 平台特有字段（POI/合集等）
  schedule_at       TIMESTAMPTZ,             -- 定时发布，NULL=立即
  priority          SMALLINT NOT NULL,       -- 1/5/9
  status            VARCHAR(16) NOT NULL,    -- pending/running/success/failed/awaiting_reauth
  sau_task_id       VARCHAR(64),             -- sau 那边的 job id
  result_url        TEXT,                    -- 发布成功后的作品页
  error_message     TEXT,
  retry_count       SMALLINT DEFAULT 0,
  enqueued_at       TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  created_by        UUID NOT NULL,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_spt_tenant_status ON social_publish_task(tenant_id, status);
CREATE INDEX idx_spt_account ON social_publish_task(account_id);
```

`platform_payload` 示例：

```json
{
  "douyin":  {"poi_id": "...", "poi_name": "...", "collection_id": "...",
              "who_can_see": "public", "allow_download": true},
  "xhs":     {"poi_id": "...", "poi_name": "...", "who_can_see": "public",
              "cover_index": 0},
  "ks":      {"who_can_see": "public", "allow_download": true}
}
```

### 3.2 配置（不新建表）

复用 `api/configs/feature/__init__.py`：

```python
SOCIAL_PUBLISH_TIER_THRESHOLDS = {
    "high":  {"min_consume_90d": 500, "concurrent": 10, "priority": 9, "max_pending": 200},
    "mid":   {"min_consume_90d": 50,  "concurrent": 5,  "priority": 5, "max_pending": 100},
    "low":   {"min_consume_90d": 0,   "concurrent": 2,  "priority": 1, "max_pending": 50},
}
SOCIAL_PUBLISH_PER_ACCOUNT_RATE = 3   # 每账号 ≤3 任务/min
SOCIAL_PUBLISH_PLATFORM_QPS     = 20  # 平台全局 ≤20 任务/min
```

阈值/并发后台可改（从 `dify_setups` 取覆盖值）。

### 3.3 sau SQLite 不动

sau 原生 `account(id, type, filePath, userName, status)` 保持原样。`filePath` 由 sau 自己组织 `cookiesFile/{platform}_{account_id}.json`，Dify 不关心。

### 3.4 文件系统隔离

```
sau_data/
└── cookies/
    ├── tenant_{tenant_id}/
    │   ├── douyin/
    │   │   ├── {sau_account_id}.json     (storage_state)
    │   │   └── ...
    │   ├── xhs/
    │   └── ks/
    └── tenant_{tenant_id_2}/
        └── ...
```

- 文件权限 **0600**
- sau 容器以**专用低权限账户**运行
- 主机层做容器隔离

---

## 4. 关键接口契约

### 4.1 Dify API（暴露给前端）

```
# 账号管理
GET    /console/api/social-publish/accounts
       → [{id, platform, display_name, avatar_url, status, last_check_at}]
       自动按 current_tenant_id 过滤

POST   /console/api/social-publish/accounts/auth/start
       body: {platform: "douyin"}
       → {session_id, qr_image_base64, expires_in: 180}

GET    /console/api/social-publish/accounts/auth/status/{session_id}  (轮询)
       → {status: "waiting"|"scanned"|"success"|"expired"|"failed",
          account?: {id, display_name, avatar_url}, message?}

DELETE /console/api/social-publish/accounts/{id}

# 任务管理
POST   /console/api/social-publish/tasks
       body: {
         accounts: [{platform, account_id}, ...],
         video_url, cover_url?,
         per_platform: {
           douyin: {title, desc, tags, poi_id?, collection_id?, ...},
           xhs:    {title, desc, tags, poi_id?, cover_index?, ...},
           ks:     {title, desc, tags, who_can_see?, ...}
         },
         schedule_at?
       }
       → {results: [{account_id, task_id?, status, message?}, ...]}

GET    /console/api/social-publish/tasks?status=&platform=&page=
POST   /console/api/social-publish/tasks/{id}/retry
POST   /console/api/social-publish/tasks/{id}/cancel
```

**为什么用轮询而不是 SSE**：sau→Dify→前端两段 SSE 串联易被 nginx/gunicorn 60s 超时切断。轮询每 2s 一次，3 分钟最多 90 次，简单稳定。

### 4.2 sau Service API（仅 Dify 后端调用）

```
POST /accounts/{sau_account_id}/check
     → {valid: bool, checked_at}

POST /login                                  (SSE)
     body: {tenant_id, platform, session_id}
     stream: {qr_base64} → {scanned} → {success, account_id, profile}

POST /postVideo
     body: {sau_account_id, tenant_id, video_url, title, desc, tags,
            platform_extras: {...}, schedule_at?}
     → {sau_task_id}                         (异步)

GET  /tasks/{sau_task_id}
     → {status, progress, result_url?, error_message?}

POST /accounts/{sau_account_id}/delete
GET  /poi/search?platform=&keyword=          (调平台 POI API)
GET  /accounts/{sau_account_id}/collections  (仅抖音)
```

### 4.3 共享契约模块（防字符串漂移）

新建 `sau_contracts/task_names.py`，**Dify 与 sau 都 import**：

```python
PUBLISH_DOUYIN = "sau.publish.douyin"
PUBLISH_XHS    = "sau.publish.xhs"
PUBLISH_KS     = "sau.publish.ks"
```

避免 `celery.send_task("xxx")` 字符串漂移导致任务消费不到。

---

## 5. 队列调度与限流

### 5.1 Celery 队列

复用 Dify 现有 Redis broker，新增专用队列：

```bash
# sau 项目根目录启动 worker
celery -A sau_celery worker \
  --queues=publish_douyin,publish_xhs,publish_ks \
  --pool=gevent --concurrency=4 \
  --loglevel=info
```

**为什么 concurrency=4 而不是 8**：Playwright 一个 Chromium 进程占 200-400MB，单机最多 4 并发跑 Playwright。"高等级=10 并发"是**全局总数**，靠横向扩 worker 容器实现。

### 5.2 等级判定（Redis 缓存 1 小时）

```python
def get_tenant_tier(tenant_id: str) -> Tier:
    cached = redis.get(f"tier:{tenant_id}")
    if cached:
        return Tier(cached)
    consume_90d = sum_consume(tenant_id, days=90)   # 复用 billing
    for name, cfg in SOCIAL_PUBLISH_TIER_THRESHOLDS.items():
        if consume_90d >= cfg["min_consume_90d"]:
            redis.setex(f"tier:{tenant_id}", 3600, name)
            return Tier(name, cfg)
```

### 5.3 三层限流

| 层 | 位置 | 目的 |
|---|---|---|
| **L1: 入队前 max_pending** | Dify API | 防单 tenant 一次塞 1000 条堵死队列 |
| **L2: tenant 并发信号量** | worker 内（Redis SETNX） | 同时只能跑 N 条 |
| **L3: 账号速率 + 平台 QPS** | worker 内（token bucket） | 防被风控/封号 |

```python
# 入队前
def enqueue_publish(task, tenant):
    tier = get_tenant_tier(tenant.id)
    pending = count_active_tasks(tenant.id)
    if pending >= tier.max_pending:
        raise QueueFullError(429)
    celery.send_task(..., priority=tier.priority)

# Worker 拿到任务
def publish_handler(dify_task_id, payload):
    tenant_id = payload["tenant_id"]
    tier = get_tenant_tier(tenant_id)

    sem_key = f"sem:tenant:{tenant_id}"
    if not redis_semaphore_acquire(sem_key, max=tier.concurrent, ttl=600):
        raise self.retry(countdown=10)

    try:
        if not redis_token_bucket_take(f"rate:account:{payload['account_id']}", rate=3, per=60):
            raise self.retry(countdown=20)
        if not redis_token_bucket_take(f"rate:platform:{payload['platform']}", rate=20, per=60):
            raise self.retry(countdown=15)
        do_publish(payload)
    finally:
        redis_semaphore_release(sem_key)
```

### 5.4 重试与失败

| 场景 | 行为 |
|---|---|
| sau 进程挂 / 网络抖动 | Celery max_retries=3，指数退避 10s/30s/2m |
| Playwright 报 cookie 过期 | task.status = `awaiting_reauth`，**不**重试 |
| 平台返回风控 | task.status = `failed`，前端可手动 retry |
| schedule_at 定时 | enqueue 时 countdown，到点 worker 拿 |

**Celery 配置**：`task_acks_late=True` + `task_reject_on_worker_lost=True`，worker kill 时任务回 broker 重派。

### 5.5 awaiting_reauth 自动恢复

扫码成功 callback：

```python
db.session.execute(update(SocialPublishTask).where(
    SocialPublishTask.account_id == account.id,
    SocialPublishTask.status == "awaiting_reauth",
).values(status="pending"))
# 批量 enqueue
```

前端弹 toast："已恢复 N 个任务"，无需用户逐条点 retry。

### 5.6 视频文件传输（OSS 预签名）

- Dify 端生成 OSS 预签名 URL（有效期 1h）
- sau worker 收到 task 后，自己 wget 到 `/tmp/{task_id}.mp4`
- 发布成功/失败都清掉
- sau 侧 `MAX_VIDEO_SIZE=2GB`，超限直接 fail

不走 HTTP 大文件转发，不走 NFS 共享盘。

---

## 6. 各平台发布字段

| 字段 | 抖音 | 小红书 | 快手 | 备注 |
|---|---|---|---|---|
| 标题 title | ✅ ≤55 | ✅ ≤20 | ✅ ≤50 | 长度限制各异 |
| 描述/正文 desc | ✅ ≤1000 | ✅ ≤1000 | ✅ ≤500 | |
| 话题 #tags | ✅ ≤5 | ✅ ≤10 | ✅ ≤5 | |
| @用户 mention | ✅ | ✅ | ✅ | |
| **POI 地点** | ✅ | ✅ | ❌ | 抖音/小红书走平台 POI 搜索 |
| 合集 collection | ✅ | ❌ | ❌ | 仅抖音 |
| 封面 cover | ✅ 自定义/截帧 | ✅ 必填首图 | ✅ 自定义 | |
| 允许下载 | ✅ | — | ✅ | |
| 谁可以看 | ✅ 公开/好友/私密 | ✅ 公开/私密 | ✅ 公开/私密 | |
| 定时发布 | ✅ ≤14 天 | ✅ ≤7 天 | ✅ ≤7 天 | |

**高频字段**（title/desc/tags）独立列，便于查询；其余进 `platform_payload` JSON。

**多平台同发**：账号区可勾任意平台任意账号，提交一次拆 N 条 task 入队。**单发就是 N=1**，零分支。**部分失败容忍**：6 条 4 成功 2 过期，不整批回滚，前端 toast 分别提示。

---

## 7. 前端 UI

### 7.1 入口

复用 `web/app/(creatorLayout)/creator/` 壳。在作品库卡片加 `[发布]` 按钮，弹右侧抽屉。

### 7.2 抽屉布局

```
┌──────────────────────────────────────┐
│  发布到平台                       ✕  │
├──────────────────────────────────────┤
│  作品预览 + 标题输入                 │
├──────────────────────────────────────┤
│  选择平台与账号（可多选）             │
│  ┌─ 抖音 ────────────────────────┐ │
│  │  ☑ 抖小妹  ✅ 上次校验1h前    │ │
│  │  ☐ 抖大哥  ⚠️已过期 [重新授权]│ │
│  │  + 添加抖音账号                │ │
│  └────────────────────────────────┘ │
│  ┌─ 小红书 / 快手  同上 ─────────┐ │
│  └────────────────────────────────┘ │
├──────────────────────────────────────┤
│  发布信息（按平台 Tab）              │
│  ┌──[抖音]──[小红书]──[快手]──┐     │
│  │ 标题 / 描述 / 话题 / @       │     │
│  │ POI / 合集 / 封面 / 谁可见   │     │
│  │ 允许下载 / 定时              │     │
│  └─────────────────────────────┘     │
│                                      │
│  ⓘ 您的等级：高 (剩余 8/10 并发)    │
│         [取消]  [立即发布 (3账号)]   │
└──────────────────────────────────────┘
```

切 Tab 第一次自动同步 title/desc/tags（用户改了之后保留各自版本）。

### 7.3 添加账号扫码流程

```
点 [+ 添加抖音账号]
  ↓
POST /auth/start  →  拿 session_id + qr_base64
  ↓
显示二维码 + 倒计时 03:00
  ↓
轮询 GET /auth/status/{session_id} 每 2s
  ↓
状态机：
  waiting    → 提示"请使用抖音 App 扫码"
  scanned    → 提示"已扫码，请在手机上确认"
  success    → ✅ 显示昵称头像，3秒自动关，刷新账号列表
  expired    → 二维码过期，[刷新]
  failed     → 错误提示，[重试]
```

### 7.4 发布历史页

复用 task-center 列表样式：

```
📹《示例视频》
抖音·抖小妹  ✅成功  2分钟前  [查看作品 →]
─────────────────────────────────────────
📹《示例视频》
小红书·红书号A  🟡发布中 (排队第 3 位)  [取消]
─────────────────────────────────────────
📹《xxx》
抖音·抖大哥  ⚠️账号过期  [重新授权并重试]
─────────────────────────────────────────
📹《yyy》
快手·快小弟  ❌失败：标题含敏感词  [编辑后重试]
```

### 7.5 i18n

新增：`web/i18n/zh-Hans/social-publish.json`、`web/i18n/en-US/social-publish.json`，遵循项目"禁止硬编码文案"。

---

## 8. 实施阶段

| 阶段 | 工作量 | 内容 | 验收 |
|---|---|---|---|
| **P0 基建** | 3-5d | sau fork + Docker 化（api + worker 两容器）；接 Dify Redis；建 `sau_contracts` 共享模块；`SAU_INTERNAL_TOKEN` 鉴权 | sau 独立起，curl `/health` 通 |
| **P1 账号管理** | 4-6d | 主库迁移 `social_publish_account`；Dify 端账号 CRUD；扫码授权（轮询）；前端账号列表 + 添加弹窗（**仅抖音先**） | 能扫码绑抖音、能列表、能删除；隔离测试：A 看不到 B |
| **P2 单平台单发** | 5-7d | 主库 `social_publish_task`；Celery 队列接通；OSS 预签名；抖音单账号发布全链路；发布历史页 | 选作品→选抖音号→发布→2 分钟内抖音上能看到 |
| **P3 队列与限流** | 3-4d | 等级判定 + Redis 缓存；信号量并发；max_pending 拒接；账号速率/平台 QPS；awaiting_reauth 自动恢复 | 模拟低等级用户 100 条被拒；高等级 priority 优先 |
| **P4 多平台 + POI/合集** | 5-7d | 接入小红书、快手；`platform_payload`；POI 搜索/合集查询；前端按平台 Tab；多平台同发 | 1 次提交 3 平台 6 账号，6 条 task 全部入队 |

**总计 20-29 工作日**（单人）；两人并行（一人 sau+Playwright，一人 Dify+前端）压到 12-16 天。

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| **平台风控** | 用户损失 + 投诉 | 单账号 ≤3 任务/min；patchright 反检测；失败不自动重试避免风控放大；后续每账号绑定固定代理 IP |
| **Playwright OOM** | sau worker 整体宕 | concurrency=4；K8s liveness 自动重启；横向扩 worker 容器 |
| **平台 UI 改版** | 整平台发不了 | 监控连续失败率 >30% 告警；sau 上游社区跟版升级；增加 `platform_changed` 状态 |
| **Cookie 文件泄露** | 全量账号被劫持 | sau 容器最小权限；目录 0600；出口防火墙限定；后续加密落盘 |
| **批量触发风控** | IP 被拉黑 | 平台 QPS 全局限制；同账号最小间隔 60s |
| **大文件 OSS 拉取慢** | 任务长时间占 worker | task timeout=10min；OSS 走内网域名 |
| **重启丢任务** | Celery prefetch 任务被 kill | `task_acks_late` + `task_reject_on_worker_lost` |
| **任务名字符串漂移** | 任务派出去没人消费 | 共享 `sau_contracts/task_names.py` 模块 |

---

## 10. 开放问题（不阻塞设计）

1. **代理 IP**：现在不上，等真的看到风控数据再加（YAGNI）
2. **加密 cookie 落盘**：P5 再说，先靠主机隔离
3. **失败任务保留多久**：建议 30 天，超期归档；先不做归档逻辑
4. **发布数据回流**（点赞/评论数）：不在本期，后续走另一个抓取服务
5. **白名单功能**（哪些 tenant 能用发布中心）：复用 `feature_service` 开关，初期对所有人开

---

## 附录 A：sau 关键发现（节选自源码调研）

```python
# uploader/douyin_uploader/main.py
async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(storage_state=account_file)
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/...")
        if await page.get_by_text("手机号登录").count() or \
           await page.get_by_text("扫码登录").count():
            return False
        return True
```

`storage_state=account_file` 是 Playwright 原生 cookie/localstorage 持久化机制。无需自己解析 cookie 字符串。

## 附录 B：sau_backend 现成接口

| 接口 | 用途 | 复用 |
|---|---|---|
| `/upload` | 文件上传，返回 ID | 不复用，我们走 OSS |
| `/login` (SSE) | 二维码登录 | ✅ 直接复用 |
| `/getValidAccounts` | 列出有效账号 | ✅ 改造为 `/accounts/check` |
| `/postVideo` | 发布视频 | ✅ 直接复用 + 加 platform_extras |
