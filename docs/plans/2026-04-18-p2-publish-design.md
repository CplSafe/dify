# P2 设计：抖音单平台真实发布

**日期**: 2026-04-18
**关联设计**: [2026-04-18-social-auto-upload-design.md](./2026-04-18-social-auto-upload-design.md) §6
**关联实施**: [2026-04-18-social-auto-upload-design.md](./2026-04-18-social-auto-upload-design.md) P2 行
**状态**: 待评审

---

## 范围

- 仅抖音；P4 再扩 xhs/ks
- 单一账号一次发布一个视频
- 字段：title（必填）、tags（可选 list[str]）、desc（可选）、publish_date（默认立即）
- POI / 合集 / 商品挂载：留 P4
- 发布是异步的（Celery）；前端拿 `task_id` 后轮询
- 视频通过 multipart 由 Dify api → sau-api 上传（sau 暂存到 tmp，发布完清理）

非范围（明确放弃）：
- 多平台并发发布（P4）
- 定时调度（DouYinVideo 已支持，但 P2 只走 immediate）
- 封面/标题图（DouYinVideo 已有参数，留 P3）
- 商品挂载（DouYinVideo 已有，留 P4）

## 端到端流程

```
[creator-works 列表]
        │  点击"发布到抖音"
        ▼
[发布抽屉] ── 用户填 title/tags/desc → POST /social-publish/tasks ─┐
                                                                    │
                                                                    ▼
                              ┌──── Dify api (controller → service) ───┐
                              │ 1. 校验 account_id 属于 tenant            │
                              │ 2. 创建 social_publish_task(status=pending) │
                              │ 3. 从 storage 下载 file_key 字节             │
                              │ 4. POST multipart 到 sau-api /postVideo:    │
                              │    files={video: bytes},                    │
                              │    data={tenant_id, sau_account_id,         │
                              │      title, tags, desc, ...}                │
                              │ 5. sau 返回 sau_task_id                     │
                              │ 6. 写回 social_publish_task.sau_task_id     │
                              │ 7. 返回给前端 {task_id}                     │
                              └─────────────────────────────────────────────┘
                                                                    │
                                                                    ▼
                              ┌──── sau-api ──────────────────────────────┐
                              │ /postVideo: 把视频写到 tmp 文件，                │
                              │   send_task('sau.publish.douyin',              │
                              │             tmp_path, account_file, payload),  │
                              │   立即返回 sau_task_id                          │
                              └────────────────────────────────────────────────┘
                                                                    │
                                                                    ▼
                              ┌──── sau-worker (prefork) ─────────────────────┐
                              │ publish_douyin task:                            │
                              │   1. 读 tmp_path 视频                            │
                              │   2. cookie_auth(account_file) → invalid 则失败  │
                              │   3. DouYinVideo(...).main()                    │
                              │   4. 删 tmp_path                                  │
                              │   5. return {success, message, current_url}      │
                              └──────────────────────────────────────────────────┘

[前端]  每 3 秒：GET /social-publish/tasks/{task_id}
        ↓
        controller → service.get_task_status:
          1. 查 social_publish_task（带 tenant 隔离）
          2. 如果 status 还非 terminal AND 有 sau_task_id：
               GET sau /tasks/{sau_task_id}
               根据 Celery state 更新本地 status
          3. 返回 {status, message, dy_url?, error_code?}
```

## 数据库

### 新表 `social_publish_tasks`

```sql
CREATE TABLE social_publish_tasks (
  id              UUID         PRIMARY KEY,
  tenant_id       UUID         NOT NULL,
  account_id      UUID         NOT NULL,                         -- FK social_publish_accounts
  work_id         UUID,                                           -- FK creator_works (可空，未来支持手动发布)
  platform        VARCHAR(16)  NOT NULL,                         -- douyin (P2)
  status          VARCHAR(16)  NOT NULL DEFAULT 'pending',       -- pending|queued|running|success|failed
  sau_task_id     VARCHAR(64),                                    -- celery task_id 写回
  payload         JSONB        NOT NULL,                         -- {title, tags, desc, ...}
  result_url      TEXT,                                           -- 抖音作品落地 URL
  error_code      VARCHAR(64),
  error_message   TEXT,
  created_by      UUID         NOT NULL,
  created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX social_publish_task_tenant_created_idx ON social_publish_tasks(tenant_id, created_at);
CREATE INDEX social_publish_task_account_idx        ON social_publish_tasks(account_id);
CREATE INDEX social_publish_task_status_idx          ON social_publish_tasks(status);
CREATE INDEX social_publish_task_sau_task_idx        ON social_publish_tasks(sau_task_id) WHERE sau_task_id IS NOT NULL;
```

> tenant_id 重复存储，service 层每次写入都从 account 的 tenant 派生，不接受请求传入。

## API 契约

### Dify api（新增）

| Method | Path | 说明 |
|---|---|---|
| POST | `/console/api/social-publish/tasks` | 创建发布任务 |
| GET | `/console/api/social-publish/tasks/<task_id>` | 查询任务状态 |
| GET | `/console/api/social-publish/tasks?account_id=&status=&limit=` | 列表（按 tenant） |

#### POST /social-publish/tasks

Body:
```json
{
  "account_id": "<row id from social_publish_accounts>",
  "work_id": "<creator_works.id>",
  "title": "...",          // 1..200 字符
  "tags": ["#美食", "#日常"], // 可选，<=10 个
  "desc": "..."             // 可选，<=2000 字符
}
```

Resp 200:
```json
{"task_id": "<uuid>", "status": "queued"}
```

Errors: 400 `invalid_payload`、404 `account_not_found`、409 `account_expired`、503 `feature_disabled`、502 `sau_unreachable`

#### GET /social-publish/tasks/{task_id}

Resp 200:
```json
{
  "task": {
    "id": "...",
    "status": "running",
    "platform": "douyin",
    "created_at": "...",
    "updated_at": "..."
  },
  "result": {
    "url": null,
    "error_code": null,
    "error_message": null
  }
}
```

终态时 result 字段填充。

### sau-api（修改）

`POST /postVideo` — 改为 **multipart/form-data**：

```
multipart parts:
  video: <binary>
  data:  JSON string with {tenant_id, sau_account_id, platform, title,
                            tags?, desc?, publish_date?}
```

Resp:
```json
{"sau_task_id": "<celery task id>"}
```

`GET /tasks/{sau_task_id}` — 已存在，返回 `{state, result?, error?}`。
确认 result 形态：
```json
{
  "sau_task_id": "...",
  "state": "SUCCESS|FAILURE|PENDING|STARTED|RETRY",
  "result": {"success": true, "current_url": "https://...", "message": "..."},
  "error":  null
}
```

## sau worker 改造

| 项 | P0/P1 现状 | P2 改造 |
|---|---|---|
| Pool | gevent | **改 prefork**（Playwright + asyncio 不能跑在 gevent monkey-patch 下） |
| concurrency | 4 | 2（每个 worker 进程一个 Chromium，2GB+ RAM each） |
| publish_douyin | stub | 真实调 `DouYinVideo` |
| 视频源 | n/a | sau-api 写到 `${SAU_TMP_DIR}/<sau_task_id>.mp4`，task 结束 unlink |
| cookie 校验 | 无 | task 启动时 `cookie_auth(account_file)` 失败立即 raise |
| 错误分类 | n/a | `cookie_invalid` / `upload_failed` / `unknown` |

### Celery task 签名

```python
@app.task(name=PUBLISH_DOUYIN, queue=PUBLISH_DOUYIN_QUEUE, bind=True)
def publish_douyin(
    self,
    tenant_id: str,
    sau_account_id: str,
    video_path: str,         # 由 /postVideo 写好的 tmp 路径
    payload: dict,           # {title, tags, desc, publish_date}
) -> dict:
    """Returns {success, current_url?, error_code?, message?}"""
```

worker 进程内：
1. `cookie_path = resolve_cookie_path(tenant_id, "douyin", sau_account_id)`
2. `asyncio.run(_run_douyin_publish(...))` — DouYinVideo 是 async
3. `os.unlink(video_path)` in finally
4. 抛出 / 返回不同 error_code 让 Dify 端能 i18n

## 视频传输：multipart（P2 选定方案）

权衡：

| 方案 | 优点 | 缺点 | P2 决策 |
|---|---|---|---|
| **A. multipart Dify→sau** | 任何 storage 后端都行；sau 不需要外部网络 | Dify api 进程吃内存 ~视频大小；50MB 视频 = ~50MB 暂存 | ✅ |
| B. presigned URL | 视频不经 api 进程 | 要求所有 storage 后端实现 presigning；本地 fs 不行 | P3 优化 |
| C. 共享 NFS/卷 | 零拷贝 | 部署门槛高 | ❌ |

multipart 限制：
- nginx `client_max_body_size`：在 Dify 网关默认 100MB；sau-api 网关需同等设置
- gunicorn timeout：上传可能要数十秒，把 Dify 的 sau client 超时调到 60s（仅 publish 路径）

## Worker pool 切换：gevent → prefork

P0/P1 用 gevent 跑 stub task。P2 起 publish_douyin 调真实 Playwright，必须切 prefork。

修改 `entrypoint-worker.sh`：
```bash
# 默认改成 prefork。env 可覆盖回 gevent 用于纯 stub 调试。
exec uv run celery -A apps.sau_worker.celery_app worker \
    --queues=publish_douyin,publish_xhs,publish_ks \
    --pool="${SAU_WORKER_POOL:-prefork}" \
    --concurrency="${SAU_WORKER_CONCURRENCY:-2}"
```

`docker-compose.yml`、`.env.example` 同步把 `SAU_WORKER_POOL` 默认改 `prefork`、`SAU_WORKER_CONCURRENCY` 默认改 `2`。

## 错误模型

Dify 域错误（`api/services/errors/social_publish.py` 新增）：

| 错误 | HTTP | code | 触发条件 |
|---|---|---|---|
| `TaskNotFoundError` | 404 | `task_not_found` | id 不存在或不属于 tenant |
| `TaskInvalidPayloadError` | 400 | `task_invalid_payload` | title 缺失等 |
| `WorkNotFoundError` | 404 | `work_not_found` | work_id 不存在或不属于 tenant |

sau worker 返回的 result：

| result 内容 | Dify 端 status | error_code |
|---|---|---|
| `{success: true, current_url}` | success | — |
| `{success: false, status: "cookie_invalid"}` | failed | `cookie_invalid` |
| `{success: false, status: "timeout"}` | failed | `upload_timeout` |
| `{success: false, ...}` | failed | `upload_failed` |
| celery state FAILURE | failed | `worker_crashed` |

cookie_invalid 时**自动**把 `social_publish_account.status` 改为 `expired`，前端列表上下次刷新就能看到红点。

## P2 阶段不解决的"已知坑"

明确写下来，避免日后翻账：

1. **多 workers 限制依旧**：sau-api 仍是 workers=1（login_sessions 还是进程内）。Celery worker 端没这个问题（Celery 自己分发）。
2. **cookies 文件并发写**：sau worker prefork 下 N 个进程，但每条 task 一个 sau_account_id，文件锁不需要（同一账号同时只能跑一个 task — 由 Dify 端串行化保证，下一段说明）。
3. **同一 account 单并发**：service 层每次创建任务前查"当前 account 是否有 status in (pending,queued,running) 的任务"，有就拒绝。这是用户合理预期（同账号不该同时发两个视频）。
4. **OSS 大文件**：>100MB 视频 P2 直接拒绝（service 层校验 `len(bytes) <= 100MB`）。生产真要支持，走 P3 的 presigned URL。
5. **publish_date 时区**：DouYinVideo 用 datetime（注意 sau 是 UTC，抖音是 Asia/Shanghai）。P2 只支持立即发布，不传 publish_date，留 P3 处理。

## 安全 / 多租户

- POST /tasks: payload 里的 `account_id`、`work_id` 都按 tenant 校验（service 调 repo.get_by_id_and_tenant）
- account 拥有的 sau_account_id 不进 payload；Dify→sau 的 multipart 由 Dify 派生
- task_id 是 uuid4；GET 一定带 tenant_id 过滤，跨租户返 404（不区分"不存在"和"无权"）
- multipart 传输的视频字节不写日志，不存第二份

## 工作量估算

| 子任务 | 估时 (h) |
|---|---|
| design 文档 | 1 |
| backend: model + migration | 1.5 |
| backend: repo (新表 + 现有 account 的"是否有 in-flight"查询) | 2 |
| backend: SauClient.post_video (multipart) + get_task | 2 |
| backend: service.publish/get_task_status + 错误映射 + 自动过期账号 | 4 |
| backend: 3 controller routes + 错误映射 | 2 |
| backend: tests (repo isolation + service flows + sau_client multipart) | 4 |
| sau-api: /postVideo 改 multipart + tmp 写文件 | 2 |
| sau-worker: 真实 publish_douyin (asyncio.run + DouYinVideo + 错误分类) | 3 |
| sau-worker: pool 切换 + Docker 改 + tests | 2 |
| frontend: 发布抽屉（标题/话题/desc + 校验 + i18n） | 4 |
| frontend: tasks 状态轮询 hook + 列表 | 3 |
| frontend: vitest tests | 2 |
| codex review × 3（backend / sau / frontend）+ 修复 | 3 |
| 端到端联调（mock + 真实 cookie） | 3 |
| **小计** | **38.5** |
| **+ 25% buffer** | **48** ≈ **6 人日** |

## 验收

- [ ] Alembic upgrade/downgrade 双向跑通
- [ ] backend 测试全绿、覆盖率 ≥ 85%
- [ ] sau worker 单测全绿（mock DouYinVideo）
- [ ] 前端 vitest 全绿
- [ ] 端到端：sau-mock + Dify api + Dify FE 跑通发布提交→任务"queued"→（mock 模拟"success"）→FE 显示"已发布"
- [ ] 同账号串行化：同一 account 已有 pending 时再次提交返 409
- [ ] cookie_invalid 时账号自动转 expired，FE 列表显示重新授权
- [ ] 视频 >100MB 被拒（400）
- [ ] codex review 通过，无 CRITICAL / 修完 HIGH
