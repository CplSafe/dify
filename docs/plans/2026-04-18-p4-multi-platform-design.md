# P4 设计：多平台 (xhs/ks) + 平台字段 + 一次发多端

**日期**: 2026-04-18
**关联**: [设计](./2026-04-18-social-auto-upload-design.md) §6 / §10；[P3](./2026-04-18-p3-queue-design.md)
**状态**: 待评审

---

## 范围

P3 之后，发布中心只支持 douyin 单条发布。P4 解锁：

1. **xhs (小红书) + ks (快手) publish worker** — 调上游 `XiaoHongShuVideo` / `KSVideo`
2. **xhs / ks 扫码授权** — sau `/login` 支持 platform=xhs 和 platform=ks
3. **平台特定字段** — 抖音 `location`、小红书 `location`；放进 `payload.platform_payload`，sau 端按平台拆开
4. **批量发布** — 一次提交可选多个 (account_id) 组合，service 拆成 N 条 SocialPublishTask 行 + N 个 sau dispatch

明确不在 P4：
- 抖音 / 小红书 的"合集 / 集合"挂载（上游 uploader 没有暴露字段，需要自己 Playwright 编排，留 P5）
- 商品挂载（同上）
- 定时调度（DouYinVideo / XHS / KS 都支持 publish_date，但 P4 只走 immediate）

---

## 架构

```
┌─ Dify api ──────────────────────────────────────────────────────────┐
│ POST /tasks (新 batch shape)                                          │
│ body:                                                                 │
│   work_id: "...",                                                     │
│   targets: [                                                          │
│     {account_id: "acc-dy-1", platform_payload: {location: "上海"}},  │
│     {account_id: "acc-xhs-1", platform_payload: {location: "北京"}}, │
│   ],                                                                  │
│   title: "...", tags: [...], desc: "..."                              │
│ ↓                                                                     │
│ TaskService.create_batch(...)  — 1 quota slot per target              │
│   for each target:                                                    │
│     resolve_account → tier check → single-flight → create row →       │
│     post_video(platform=account.platform, ...)                        │
│ returns {task_ids: ["t-1", "t-2"], failed: {...}}                     │
└──────────────────────────────────────────────────────────────────────┘

┌─ sau /postVideo (unchanged wire) ─┐
│ data envelope now carries:         │
│   "platform": douyin|xhs|ks,        │
│   "platform_payload": {location?, ..} │
└────────────────────────────────────┘

┌─ sau worker ─────────────────────────────────────────────────────────┐
│ publish_douyin: cookie_auth(douyin) → DouYinVideo + LocationPatch    │
│ publish_xhs:    cookie_auth(xhs)    → XiaoHongShuVideo + LocationPatch│
│ publish_ks:     cookie_auth(ks)     → KSVideo                         │
│  (KS uploader has no location call — payload.location ignored)        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. sau 端 publish_xhs / publish_ks

新两个 worker task 文件，与 `publish_douyin.py` 同构：

| 文件 | 上游 cookie_auth | 上游 Video class | 上游 cookie_gen |
|---|---|---|---|
| `apps/sau_worker/tasks/publish_douyin.py` | `uploader.douyin_uploader.main.cookie_auth` | `DouYinVideo` | `douyin_cookie_gen` |
| `apps/sau_worker/tasks/publish_xhs.py` (改) | `uploader.xiaohongshu_uploader.main.cookie_auth` | `XiaoHongShuVideo` | `xiaohongshu_cookie_gen` |
| `apps/sau_worker/tasks/publish_ks.py` (改) | `uploader.ks_uploader.main.cookie_auth` | `KSVideo` | (no cookie_gen — KS uploader没有暴露) |

> **KS 扫码登录限制**：`uploader.ks_uploader.main` 暴露 `ks_setup` 但没有 `ks_cookie_gen`；P4 sau `/login` 对 KS **暂时返回 501**，写到 docs/UPGRADE.md，待上游补齐。XHS 完整支持。

为了避免重复，把三个 worker task 共享的"limit + concurrency + cookie 解析 + 下载 + 调用 Video class + finally 清理 tmp"逻辑抽成 `apps/sau_worker/_publish_runner.py`：

```python
class PlatformBinding(NamedTuple):
    name: Literal["douyin", "xhs", "ks"]
    cookie_auth: Callable[[str], Awaitable[bool]]
    video_cls: type
    apply_platform_extras: Callable[[uploader_instance, dict], None] | None  # P4

DOUYIN = PlatformBinding(...)
XHS = PlatformBinding(...)
KS = PlatformBinding(...)

def run_publish(self, *, binding, tenant_id, sau_account_id, ...): ...
```

每个 task 文件就只有：

```python
@app.task(name=PUBLISH_XHS, queue=PUBLISH_XHS_QUEUE, bind=True)
def publish_xhs(self, ...):
    return run_publish(self, binding=XHS, ...)
```

### 1.1 平台字段透传

新 task kwarg `platform_payload: dict[str, Any]` 来自 Dify。worker 把它解开：

| key | douyin | xhs | ks |
|---|---|---|---|
| `location` | 调 `set_location()` (子类 patch) | 调 `set_location()` | 忽略 |

### 1.2 子类 patch 方式

DouYinVideo / XiaoHongShuVideo 的 `upload()` 方法没在标题填写后调 `set_location`。我们写：

```python
class DouYinVideoWithLocation(DouYinVideo):
    async def upload(self, *args, **kwargs):
        # Monkey-style: 在父类 upload 末尾追加 set_location 调用
        await super().upload(*args, **kwargs)
```

这会失败，因为 super().upload() 已经点了"发布"。**正确方式**：上游 upload 中是分阶段的，Title fill ➜ tags ➜ "发布"按钮。`set_location` 必须在"发布"前调。所以重写不可行 — 需要 patch 单个 step。

简化方案：**P4 仅支持 location 通过 desc 拼接**（在 desc 末尾自动加 "📍 上海"）。这是次优体验但**零侵入**上游、安全可发。

> **明确决策**：把 `set_location` 真正接进上游 upload pipeline 留给 P5（要么向 dreammis 提 PR，要么 fork upstream upload 方法）。P4 就走"location 拼到 desc"的简易路径，并明文写到 i18n 和 release note。

### 1.3 task 信号

worker 返回值新增 `error_code` 候选 `platform_unsupported`（如 KS + cookie_gen 调用），FE i18n 加。

---

## 2. sau /login 支持 xhs

`apps/sau_api/routers/login_sse.py` 改：

```python
_PLATFORM_TO_COOKIE_GEN = {
    "douyin": ("uploader.douyin_uploader.main", "douyin_cookie_gen"),
    "xhs":    ("uploader.xiaohongshu_uploader.main", "xiaohongshu_cookie_gen"),
}

if req.platform == "ks":
    raise HTTPException(400, "ks scan-to-auth not yet supported")
```

cookie_paths.py 已支持三个 platform（P0 起）。无需变更。

---

## 3. Dify backend 多平台支持

### 3.1 service 改动

`SUPPORTED_PLATFORMS_P2 = ("douyin",)` → `SUPPORTED_PLATFORMS_P4 = ("douyin", "xhs", "ks")`。

`CreateTaskRequest` 增加 `platform_payload: dict | None = None` 字段。`_validate_payload` 透传 `platform_payload`（不验证内容，sau 端自己校验）。

### 3.2 batch 接口

新 method `create_batch(tenant_id, created_by, request: CreateBatchRequest) -> CreateBatchResponse`：

```python
@dataclass(frozen=True)
class CreateBatchTarget:
    account_id: str
    platform_payload: dict | None = None

@dataclass(frozen=True)
class CreateBatchRequest:
    work_id: str
    targets: list[CreateBatchTarget]
    title: str
    tags: list[str] | None
    desc: str | None

@dataclass(frozen=True)
class CreateBatchResponse:
    task_ids: list[str]            # 创建成功的 (按 targets 顺序)
    failed: list[dict[str, str]]   # [{account_id, error_code, message}]
```

策略：
- targets 限 ≤ 10（防滥用，写 const）
- 按顺序串行创建（避免抢同一 account 的 single-flight 锁）
- 每个 target 独立创建 + 独立 sau dispatch；任一失败不阻塞下一个
- 全部 failed 时 raise `TaskInvalidPayloadError`，否则返 `{task_ids, failed}` 给前端

新接口：`POST /console/api/social-publish/tasks/batch`。原 `POST /tasks` 保留向后兼容（单 target 等价）。

### 3.3 platform_payload 流向

```
Dify FE
  └→ POST /tasks (payload.platform_payload={location: "..."})
       └→ TaskService.create_task → SauClient.post_video(payload={..., platform_payload})
            └→ sau /postVideo (envelope.platform_payload)
                 └→ Celery dispatch → publish_douyin(payload={..., platform_payload})
                      └→ run_publish 解开 payload["platform_payload"]["location"]
```

### 3.4 不变量

- Service 层一次只暴露 `create_task`（单 target）+ `create_batch`；FE 永远走 batch 接口（即使只有一条）
- batch 内每个 task 都重新 acquire quota slot；超过 max_pending 后续 target 全部 fail with `task_quota_exceeded`
- 同账号已有 in-flight：`task_already_in_flight` 走 failed 返回，不阻塞其他 target
- platform_payload 是黑盒透传：service 只校验是 dict 类型，不验内容；越权值由 sau 端忽略

---

## 4. Dify FE 改动

`PublishDrawer`：

- "发布账号" select 改成 multi-select（chip 列表，可加/删；按平台分组）
- 每个选中 account 展开一个 "更多设置" 折叠面板，显示该平台支持的字段：
  - douyin / xhs: location 输入框
  - ks: 占位提示"该平台无额外字段"
- 提交：组装 `targets: [{account_id, platform_payload: {location?}}]`，调 `createSocialPublishBatch(...)`
- 进度：成功跳转到任务列表（不再单条轮询，因为可能 N 条；列表页用现有 `listSocialPublishTasks` 自动刷新）
- 当某 target failed：toast 显示首个错误 + 链接到任务列表

`useSystemFeatures().social_publish_enabled` 不变。`accountList` 列表展示已支持 xhs / ks 列（i18n 已经预留）。

i18n 新 key：

```
publish.targets.add: "添加账号"
publish.targets.empty: "请选择至少一个账号"
publish.platformExtras.location: "地理位置"
publish.platformExtras.locationPlaceholder: "上海 / 杭州 / ..."
publish.platformExtras.kuaishou: "快手暂无额外字段"
publish.batchPartial: "{{ok}} 条已发出，{{fail}} 条失败"
auth.errors.platform_unsupported_for_login: "该平台暂未支持扫码登录"
```

---

## 5. 数据库

无新表/新列。已有 `social_publish_task.payload JSONB` 容纳 `platform_payload`。

---

## 6. 错误新增

| 错误 | HTTP | code |
|---|---|---|
| `BatchTooLargeError` | 400 | `batch_too_large` |
| `BatchEmptyError` | 400 | `batch_empty` |

复用 P3 已有的 task_*. 错误。

---

## 7. 测试

- backend
  - service.create_batch: 正常多 target / 部分失败 / 全部失败 raise / quota exhausted mid-batch
  - SUPPORTED_PLATFORMS_P4 包含 douyin/xhs/ks
  - platform_payload 进 payload JSON 透传
- sau
  - publish_xhs / publish_ks 单测（mock 上游 module）
  - run_publish 共享代码：location → desc 拼接
- FE
  - PublishDrawer 多 target chip add/remove
  - 平台字段折叠面板按 platform 渲染对应表单
  - 部分失败 toast

---

## 8. 工作量估算

| 任务 | 估时 (h) |
|---|---|
| design | 1 |
| sau: 抽 _publish_runner + 改 douyin/xhs/ks 三个 task | 3 |
| sau: /login 接入 xhs | 1 |
| sau: 新测试 (xhs/ks tasks + runner) | 2 |
| backend: SUPPORTED_PLATFORMS_P4 + platform_payload 透传 | 1 |
| backend: create_batch service + repo 不变 | 3 |
| backend: POST /tasks/batch route + 错误 | 2 |
| backend: 测试 (batch + 多平台 service path) | 3 |
| frontend: 多 target chip + 平台字段表单 | 4 |
| frontend: vitest | 2 |
| codex review × 3 + 修复 | 3 |
| **小计** | **25** |
| **+ 25% buffer** | **31** ≈ **4 人日** |

---

## 9. 验收

- [ ] 抖音 + 小红书账号同时绑定后，从 PublishDrawer 一次提交两条任务，列表显示 2 行
- [ ] 抖音 location 字段拼到 desc 末尾发布成功
- [ ] KS uploader 调通（mock cookie），任务列表 success
- [ ] sau `/login platform=ks` → 400 `ks scan-to-auth not yet supported`
- [ ] sau `/login platform=xhs` → 真实 cookie_gen（mock 模式仍 stub）
- [ ] batch 内单 target failed 不阻塞其他 target
- [ ] codex review HIGH 全修
