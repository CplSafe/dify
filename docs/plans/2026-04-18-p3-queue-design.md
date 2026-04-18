# P3 设计：租户分级 + 限流 + 大视频走 presigned URL

**日期**: 2026-04-18
**关联**: [2026-04-18-social-auto-upload-design.md](./2026-04-18-social-auto-upload-design.md) §5；P2 [设计](./2026-04-18-p2-publish-design.md) "已知坑" 第 4 条
**状态**: 待评审

---

## 范围

P2 之后还遗留三类压力：

1. **公平性**：单租户提交几百个发布会霸占整个 Celery worker 队列，把别人的扫码授权 / 单条发布也拖慢
2. **滥用 / 抖音限流**：同一账号短时间内连发会被抖音判定异常
3. **大视频**：multipart 把字节穿过 Dify api 进程，>100MB 直接拒绝

P3 解决：

- 按 tenant 90 天总消费划 **3 档**，决定 Celery 优先级 + 并发上限 + 待处理上限
- per-account **token bucket** 限流（≤3 / min），平台总 QPS 兜底（≤20 / min）
- storage 后端可选地暴露 **presigned URL**；service 优先走 URL，回退 multipart

明确不在 P3：
- ML/规则识别异常账号（黑名单）
- 多平台并发（P4）
- 重试策略 / 调度时间窗（P4 / P5）

---

## 架构概览

```
┌────────── Dify api ──────────┐                  ┌────── sau-api / worker ───────┐
│ controller: POST /tasks      │                  │ /postVideo:                    │
│   ↓                          │                  │   • 接受 video (multipart) OR  │
│ TaskService.create_task:     │  HTTP            │     video_url (新)              │
│   1. resolve account/work    │ ───────────────► │   • 写到 SAU_TMP_DIR            │
│   2. tier = TierResolver()   │                  │   • Celery send_task with       │
│   3. quota check (max_pending│                  │     priority = N                 │
│      vs tier limit)          │                  │                                  │
│   4. token bucket guard      │                  │ Celery worker:                  │
│      (per-account ≤3/min)    │                  │   • 队列读取（PRIO 0..9）         │
│   5. choose transport:       │                  │   • per-account semaphore       │
│      - presigned URL when    │                  │     (Redis SET NX, ttl=10m)     │
│        storage支持 + 文件>5MB │                  │   • run DouYinVideo             │
│      - multipart otherwise   │                  │                                  │
│   6. POST /postVideo with    │                  │                                  │
│      priority header         │                  │                                  │
└──────────────────────────────┘                  └────────────────────────────────┘
```

---

## 1. 租户分级（tier）

### 1.1 表

```python
SOCIAL_PUBLISH_TIER_THRESHOLDS = {
    "high":  {"min_consume_90d": 500, "concurrent": 10, "priority": 9, "max_pending": 200},
    "mid":   {"min_consume_90d": 50,  "concurrent": 5,  "priority": 5, "max_pending": 100},
    "low":   {"min_consume_90d": 0,   "concurrent": 2,  "priority": 1, "max_pending": 50},
}
```

字段含义：

- `min_consume_90d`: 90 天 BillingRecord deduction 总额（CNY）。tier 取最高满足项
- `concurrent`: 同一租户同时跑的 publish 任务数（sau worker 端用）
- `priority`: Celery 任务优先级（0 最低、9 最高；与 redis-celery 一致）
- `max_pending`: 该租户队列中"未终结"任务数上限（status in pending/queued/running）

### 1.2 实现

新文件 `api/services/social_publish_tier.py`：

```python
@dataclass(frozen=True)
class TenantTier:
    name: Literal["high", "mid", "low"]
    concurrent: int
    priority: int
    max_pending: int

class TierResolver:
    """Resolve a tenant_id → TenantTier with a 5-min Redis cache.

    Cache key: ``sau:tier:{tenant_id}``. The 5-min TTL trades a bit of
    staleness for keeping aggregate(BillingRecord) off the hot path."""
    def get_tier(self, tenant_id: str) -> TenantTier: ...
    def invalidate(self, tenant_id: str) -> None: ...
```

90 天聚合：

```sql
SELECT COALESCE(SUM(amount), 0)
FROM billing_records
WHERE tenant_id = :tenant_id
  AND record_type = 'deduction'
  AND created_at >= NOW() - INTERVAL '90 days';
```

> 历史 BillingRecord 行有 `tenant_id IS NULL` — 这些归到 `low`（无法定位租户的消费天然就该最低优先）。

### 1.3 quota 校验在 service 怎么落

`TaskService.create_task` 在 single-flight Redis 锁 **之前** 加：

```python
tier = self._tier_resolver.get_tier(tenant_id)
pending_count = self._tasks.count_active_for_tenant(tenant_id)
if pending_count >= tier.max_pending:
    raise TaskQuotaExceededError(
        f"tenant has {pending_count} in-flight tasks (limit {tier.max_pending})"
    )
```

新 repo 方法 `count_active_for_tenant(tenant_id)` 直接 SQL `COUNT(*) WHERE tenant_id=? AND status IN (active...)`。

---

## 2. Celery 优先级

`SauClient.post_video` 增加 `priority` 参数；sau-api 的 `/postVideo` 透传到 `send_task(..., priority=N)`。

Celery + Redis broker 支持 priority 队列（需要 `broker_transport_options={'priority_steps': list(range(10)), 'sep': ':'}`）。

修改 `apps/sau_worker/celery_app.py`：

```python
app.conf.broker_transport_options = {
    "priority_steps": list(range(10)),
    "sep": ":",
    "queue_order_strategy": "priority",
}
app.conf.task_default_priority = 5
```

`/postVideo` 拿到 priority（0-9，默认 5），传给 `send_task(name, kwargs=..., queue=..., priority=priority)`。

> Dify 端的 `priority` 来自 tier 表。**新接口字段**：`POST /tasks` body 不接受 priority（防越权），后端按 tier 派生。

---

## 3. per-account 限流（token bucket）

### 3.1 sau worker 端做，不放 Dify

理由：限流是为了**保护抖音侧不被风控**，是 sau worker 知识。Dify 端做的话，跨多 worker 进程不好协调。

### 3.2 实现

新模块 `apps/sau_worker/rate_limit.py`：

```python
class TokenBucket:
    """Redis-backed sliding window. Reuses Dify's RateLimiter pattern but
    sharded by sau_account_id."""

    def __init__(self, redis_client, *, prefix: str, capacity: int, window_sec: int): ...
    def try_acquire(self, key: str) -> bool: ...   # True if under cap
    def wait_or_acquire(self, key: str, *, max_wait_sec: int = 30) -> bool: ...
```

`publish_douyin` task 启动时：

```python
bucket = TokenBucket(redis_client, prefix="sau:tb:douyin", capacity=3, window_sec=60)
if not bucket.wait_or_acquire(sau_account_id, max_wait_sec=120):
    return {"success": False, "status": "rate_limited",
            "message": "per-account rate limit (≤3/min)"}
```

平台兜底（≤20/min, key=`sau:tb:douyin:_platform`）类似。

> Dify 端把 `rate_limited` 映射成 `error_code=upload_rate_limited`，前端文案"发布过于频繁，已自动重试"。FE 不重试，由 Celery 任务自身的 `bucket.wait_or_acquire` 做阻塞等待 — worker 死等不超过 `max_wait_sec`。

### 3.3 per-tenant concurrent 在 worker 端做

Redis 自旋信号量：每个 task 启动时 `INCR sau:concurrent:tenant:{id}`，超过 tier.concurrent 就阻塞重试 N 次后失败。
任务结束 `DECR`。崩溃保护：每个 INCR key 同时设 EX 600s。

Redis Lua 脚本保证原子性：

```lua
-- KEYS[1]=counter key, ARGV[1]=limit, ARGV[2]=ttl
local n = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
if n > tonumber(ARGV[1]) then
  redis.call('DECR', KEYS[1])
  return 0
end
return n
```

放 `apps/sau_worker/concurrency.py`，类型 `TenantConcurrencyGate(redis_client, *, prefix, ttl_sec)`。

---

## 4. presigned URL 视频传输

### 4.1 storage 抽象扩展

```python
# api/extensions/storage/base_storage.py
def supports_presigned_url(self) -> bool:
    return False

def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
    raise NotImplementedError
```

实现两端：

| 后端 | 实现要点 |
|---|---|
| AWS S3 | `boto3.client('s3').generate_presigned_url('get_object', ...)` |
| Aliyun OSS | `bucket.sign_url('GET', key, expires_in)` |

其余后端（local fs / azure / gcs / huawei / baidu / tencent / clickzetta / opendal）保留默认 `supports_presigned_url = False`，自动回退 multipart。

### 4.2 service 选择路径

`TaskService.create_task`：

```python
THRESHOLD_BYTES = dify_config.SOCIAL_PUBLISH_PRESIGNED_THRESHOLD_BYTES  # default 5MB

# Decide BEFORE we read the bytes — calls storage.exists/head only.
prefer_url = (
    storage.supports_presigned_url()
    and dify_config.SOCIAL_PUBLISH_PREFER_PRESIGNED
    and self._estimate_size(work.file_key) >= THRESHOLD_BYTES
)

if prefer_url:
    url = storage.generate_presigned_url(
        work.file_key, expires_in=3600
    )
    response = self._sau.post_video(
        ..., video_url=url, video_bytes=None,
    )
else:
    # Existing multipart path (capped at SOCIAL_PUBLISH_MAX_VIDEO_BYTES).
    video_bytes, video_filename = self._load_video(work)
    response = self._sau.post_video(
        ..., video_bytes=video_bytes, video_filename=video_filename,
    )
```

`_estimate_size(key)` 用 storage `head_object`（S3）或 `OSS bucket.head_object`，回退 `load_once+len` 然后丢弃 — 后者只在阈值附近少数情况发生。

### 4.3 SauClient 改动

`post_video` 签名变成（向后兼容）：

```python
def post_video(
    self,
    *,
    tenant_id: str,
    platform: Platform,
    sau_account_id: str,
    payload: dict[str, Any],
    priority: int = 5,
    video_bytes: bytes | None = None,
    video_filename: str | None = None,
    video_url: str | None = None,
    timeout_seconds: float | None = None,
) -> SauPublishResponse:
    if video_bytes is None and video_url is None:
        raise ValueError("either video_bytes or video_url required")
    ...
```

multipart 模式（现状）：把 `video_url` 也作为 form field，但 sau 端会优先 video file。
URL 模式：不传 file，data envelope 多一个 `video_url` 字段。

### 4.4 sau-api `/postVideo` 改动

```python
@router.post("/postVideo")
async def post_video(
    video: UploadFile | None = File(default=None),
    data: str = Form(...),
):
    envelope = json.loads(data)
    video_url = envelope.get("video_url")
    if video is None and not video_url:
        raise HTTPException(400, "either video file or video_url required")
    ...
```

如果 envelope 有 `video_url`：worker 收到 `video_path=None` + `video_url=...`，自己流式下载到 SAU_TMP_DIR。
如果有 video file：保持 P2 行为。

worker：

```python
if video_path is None and video_url:
    video_path = _download_video_url(video_url, dest=tmp_root / f"{task_id}.mp4")
    # Stream with httpx; 600s timeout; size cap from env (default 1GB).
```

下载用 sau worker 自己的 httpx，不需要 Dify 的 `X-Sau-Token`（presigned URL 自己鉴权）。

---

## 5. 数据库变更

无新表。复用：

- `BillingRecord` (tenant_id + record_type='deduction' + amount)：tier 计算
- `social_publish_tasks.status` (ACTIVE_TASK_STATUSES)：max_pending 计数

新 config 项（`api/configs/feature/__init__.py`）：

```python
SOCIAL_PUBLISH_PREFER_PRESIGNED: bool = True
SOCIAL_PUBLISH_PRESIGNED_THRESHOLD_BYTES: int = 5 * 1024 * 1024
SOCIAL_PUBLISH_PRESIGNED_TTL_SECONDS: int = 3600
SOCIAL_PUBLISH_TIER_CACHE_TTL_SECONDS: int = 300
```

新错误：

| 错误 | HTTP | code |
|---|---|---|
| `TaskQuotaExceededError` | 429 | `task_quota_exceeded` |

---

## 6. 不变量 / 回归

- **多租户**：tier 计算的 SQL 只按 tenant_id 过滤；不会跨租户求和。
- **优先级越权**：FE 不能传 `priority`；service 永远派生。
- **presigned URL 泄漏**：1h TTL；`_to_dict` 不返回 URL（仅在 service → sau 链路存在）。
- **取消支持**：P3 不引入；`bucket.wait_or_acquire` 有上限，不会无限等。
- **历史 BillingRecord tenant_id NULL**：低 tier，不影响新数据。
- **storage 后端不支持 presigned**：`supports_presigned_url=False`，路径自动回退；不影响现有部署。

---

## 7. 测试

- **新单测**：
  - `TierResolver`: 各阈值边界 / 无消费记录 / 缓存命中 / invalidate
  - `TenantConcurrencyGate`: 计数原子性 / TTL 自动释放 / 限制触发
  - `TokenBucket`: window 滑动 / wait_or_acquire 阻塞 / 平台 vs account 分桶
  - `TaskService.create_task`: max_pending 拒绝 / priority 派生 / video_url vs multipart 路径选择
  - `SauClient.post_video`: 三种参数组合（bytes / url / 缺一不可）
  - `_download_video_url`: 大小上限 / 超时 / 200/404
  - storage `generate_presigned_url`: AWS/Aliyun mock

- **e2e**：sau-mock 增加 `video_url` 路径（拉一个 fake URL → 写到 tmp）。

- **codex review**：3 个仓库各一次，重点 max_pending 竞争、presigned URL 鉴权、Lua 脚本注入面。

---

## 8. 工作量估算

| 子任务 | 估时 (h) |
|---|---|
| design doc | 1 |
| TierResolver + repo.count_active_for_tenant + 单测 | 4 |
| Celery priority 配置 + sau /postVideo 透传 | 2 |
| TokenBucket + TenantConcurrencyGate + 单测 | 5 |
| publish_douyin 集成限流 + 信号量 + rate_limited 错误码 | 3 |
| storage.generate_presigned_url 抽象 + AWS/Aliyun 实现 + 单测 | 5 |
| service 选择路径 + sau client 三种参数组合 + 单测 | 4 |
| sau /postVideo 接受 video_url + worker 下载 + 单测 | 4 |
| 错误新增（rate_limited / quota_exceeded）+ FE i18n 补 | 1 |
| 端到端联调 mock + 真 S3 | 4 |
| codex review × 3 + 修复 | 4 |
| **小计** | **37** |
| **+ 25% buffer** | **47** ≈ **6 人日** |

---

## 9. 阶段验收

- [ ] high tier 任务的 sau celery `priority=9`，low tier `priority=1`，可用 `celery inspect` 确认
- [ ] 同一抖音账号 1min 内连发 4 条：第 4 条进入 token bucket 等待；超过 max_wait 返 `rate_limited`
- [ ] tenant tier=low：第 51 条任务返 429 `task_quota_exceeded`
- [ ] S3 后端 + 10MB 视频：service 走 presigned URL，Dify api 进程内存峰值 <50MB
- [ ] 本地 fs 后端：service 自动回退 multipart
- [ ] 历史无消费的租户走 low tier 不报错
- [ ] codex review HIGH 全修
