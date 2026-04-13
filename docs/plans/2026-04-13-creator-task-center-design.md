# Creator 任务中心设计文档

**日期：** 2026-04-13  
**状态：** 待实现

---

## 功能概述

在 Creator 页面右上角添加「任务中心」入口，点击后从右侧滑出抽屉面板。任务中心显示当前用户所有的 chatflow 任务（进行中和已完成）。用户关闭页面后任务继续在服务端运行，重新打开可恢复到对应创意页继续交互。

---

## 后端设计

### 数据模型

新增表 `creator_tasks`：

```sql
CREATE TABLE creator_tasks (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          VARCHAR NOT NULL,
  app_id           VARCHAR NOT NULL,
  installed_app_id VARCHAR NOT NULL,
  conversation_id  VARCHAR,
  workflow_run_id  VARCHAR,
  status           VARCHAR NOT NULL DEFAULT 'running',
                   -- pending | running | waiting_input | completed | failed
  title            VARCHAR(200),
  created_at       TIMESTAMP DEFAULT NOW(),
  updated_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_creator_tasks_user_status
  ON creator_tasks(user_id, status, created_at DESC);

CREATE INDEX idx_creator_tasks_conversation
  ON creator_tasks(conversation_id);
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/creator/tasks` | 发起任务时创建记录 |
| GET | `/creator/tasks` | 获取任务列表（最近 20 条） |
| PATCH | `/creator/tasks/:id` | 更新任务状态（带乐观锁） |
| GET | `/creator/tasks/:id` | 获取单个任务详情 |

**POST 请求体：**
```json
{
  "app_id": "xxx",
  "installed_app_id": "xxx",
  "conversation_id": "xxx",
  "workflow_run_id": "xxx",
  "title": "小红书爆款文案生成"
}
```

**GET `/creator/tasks` 响应：**
```json
{
  "tasks": [
    {
      "id": "uuid",
      "installed_app_id": "xxx",
      "conversation_id": "xxx",
      "status": "running",
      "title": "小红书爆款文案生成",
      "created_at": "2026-04-13T10:00:00Z",
      "updated_at": "2026-04-13T10:01:00Z"
    }
  ],
  "total": 15,
  "in_progress_count": 2
}
```

**PATCH 请求体（乐观锁）：**
```json
{
  "status": "completed",
  "last_updated_at": "2026-04-13T10:00:00Z"
}
```
版本不匹配返回 `409 Conflict`，前端重新 GET 后重试。

### 并发与限制

- 每用户最多 **10 条并发进行中**任务（running + waiting_input 合计）
- 超出返回 `429`，前端提示「当前进行中任务已达上限」
- 已完成任务总量超 50 条自动删除最旧的
- `GET /creator/tasks` 每次最多返回最近 20 条

### 超时清理

Celery 定时任务（每小时）：超过 24 小时仍处于 running/waiting_input 的任务自动标记 failed。

---

## 前端设计

### 入口

`web/app/(creatorLayout)/layout.tsx` 右上角图标按钮 + badge（进行中数量，为 0 不显示）。

### 抽屉面板

```
┌─────────────────────────────┐
│ 任务中心              [×]   │
├─────────────────────────────┤
│ [进行中 (2)]  [已完成 (5)]  │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │ 🔄 小红书爆款文案生成    │ │
│ │ 等待输入 · 2分钟前      │ │
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ ⏳ TikTok视频脚本       │ │
│ │ 处理中 · 刚刚           │ │
│ └─────────────────────────┘ │
│ ┌─────────────────────────┐ │
│ │ ✅ 品牌故事策划          │ │
│ │ 已完成 · 昨天           │ │
│ └─────────────────────────┘ │
└─────────────────────────────┘
```

### 点击任务行为（C 方案）

- **running / waiting_input** → 跳转 `/creator/installed/[installedAppId]?conversationId=xxx`，用 conversationId 恢复对话，waiting_input 自动滚动到 Human Input 表单
- **completed** → 跳转 creator-works 对应条目或抽屉内预览

---

## 状态同步机制

### 发起任务

```
用户点击发送
  → POST /creator/tasks { status: running, ... }
  → 启动 chatflow SSE
  → 监听事件：
      workflow_finished     → PATCH status: completed
      human_input_requested → PATCH status: waiting_input
      workflow_failed       → PATCH status: failed
```

### 恢复任务

```
点击进行中任务
  → 取 conversationId + installedAppId
  → 跳转 /creator/installed/[installedAppId]?conversationId=xxx
  → 页面检测 URL conversationId，恢复历史对话
  → waiting_input: 自动滚动到 Human Input 表单
  → running: 重连 SSE 或显示处理中 loading
```

---

## 性能与并发

### 自适应轮询

- 页面可见 + 有进行中任务 → 每 5 秒轮询
- 页面隐藏 → 停止，回来立即触发一次
- 无进行中任务 → 停止轮询

### 前端请求去重

```typescript
let isFetching = false
const fetchTasks = async () => {
  if (isFetching) return
  isFetching = true
  try { await GET('/creator/tasks') }
  finally { isFetching = false }
}
```

### 后端乐观锁

PATCH 时校验 `updated_at`，不匹配返回 409，前端重新 GET 后重试。

### 边界情况

| 场景 | 处理方式 |
|------|---------|
| 网络断开后任务完成 | 下次轮询时更新状态 |
| 多标签页同时操作 | 乐观锁 + 409 重试 |
| workflow_run_id 丢失 | 用 conversation_id 反查 |
| 任务超过 24 小时 | Celery 定时标记 failed |
| 并发进行中超 10 条 | 后端 429，前端提示用户 |

---

## 涉及文件

### 新增（后端）

| 文件 | 说明 |
|------|------|
| `api/models/creator_task.py` | SQLAlchemy 数据模型 |
| `api/controllers/web/creator_task.py` | API 控制器 |
| `api/services/creator_task_service.py` | 业务逻辑（并发限制、乐观锁） |
| `api/migrations/versions/xxx_add_creator_tasks.py` | Alembic DB 迁移 |

### 新增（前端）

| 文件 | 说明 |
|------|------|
| `web/app/components/creator/task-center/index.tsx` | 入口按钮 + badge |
| `web/app/components/creator/task-center/drawer.tsx` | 抽屉面板 |
| `web/app/components/creator/task-center/task-item.tsx` | 任务卡片 |
| `web/service/creator-task.ts` | API 调用封装 |
| `web/hooks/use-creator-tasks.ts` | 轮询 + 状态管理 hook |

### 修改

| 文件 | 改动说明 |
|------|---------|
| `api/controllers/web/creator.py` | 注册新路由 |
| `web/app/(creatorLayout)/layout.tsx` | 加任务中心入口 |
| `web/app/components/creator/installed-app-page.tsx` | 发起/更新任务记录 |
| `web/app/(creatorLayout)/creator/installed/[installedAppId]/page.tsx` | 支持 `?conversationId=` 恢复对话 |
