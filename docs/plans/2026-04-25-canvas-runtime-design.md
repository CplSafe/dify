# Canvas Runtime — 设计文档

**日期**: 2026-04-25
**状态**: 待评审
**作者**: 与用户对话沉淀

## 背景

现有 chatflow debug 是「右侧 trace 列表」形态：用户聊天，节点执行作为日志列在消息下方。这适合调试，但对最终用户不直观。

用户希望反过来：**画布即运行时**。用户进入页面看到 ReactFlow 画布，输入框居中在底部；发送后节点和连线一段段「画」出来；遇到允许编辑的节点会暂停，用户在画布上直接改输入/输出再继续。

这与 ComfyUI / n8n 的运行时形态接近，是一个独立于 chatflow debug 的新交付面。

## 目标

1. 用户进入页面看到空画布 + 底部输入框
2. 发送后 chatflow 节点和边按事件流逐个出现
3. 节点开了 `allow_user_edit_*`（M3）或是 Human Input 节点 → 流暂停，用户在画布上交互
4. 「继续」直接走、「编辑后继续」复用 M6 modal 改完再走
5. 一次完整运行可命名保存，下次打开重现快照（节点 + 输入输出）
6. 输入框结构留好 `@` / `/` slash menu 给后续素材库

## 非目标

- 重写 chatflow 引擎或 Pipeline
- 实现完整素材库（这次只做 slash menu UI 占位）
- 多人协作 / 实时同步
- 在新页面里编辑工作流模板（普通 creator 越权防护，画布编辑入口仍然在管理员侧）

## 关键决策

- **画布组件 fork**（用户决定 2026-04-25）：新建 `web/app/components/canvas-runtime/`，从 `web/app/components/workflow/` 抽取必要的画布、节点、边渲染组件复制过去。运行时画布后续会改样式（圆角、暂停态高亮、底部输入框等），不能反向污染后台工作流画布。代价是节点类型新增/改动时两边要同步，但通过共享 `BlockEnum` + `nodes/<type>/` 配置文件可以把同步成本控制在样式层。
- **暂停机制** = `allow_user_edit_*` (M3) ∪ Human Input 节点。前者复用现有 flag，后者复用现有节点类型，零新概念。
- **保存粒度** = 整次运行快照，复用 `workflow_run` + `workflow_node_executions`。新表 `user_canvases` 只存 `(title, source_run_id)` 指针，不复制数据。
- **越权防护**：新路由属于 creator 白名单，但画布编辑动作（删节点、改连线）后端拒绝。普通 creator 只能在画布上看 + 改节点输入输出。

## 里程碑

| ID  | 主题                           | 内容简述                                                                                              |
| --- | ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| CR1 | 后端：节点级暂停 + resume API  | chatflow 引擎在 `node_finished` 后检测 flag 即暂停；新 endpoint resume-from 复用 M1/M7 dispatch 路径 |
| CR2 | 后端：user_canvases 表 + CRUD  | `(id, tenant_id, app_id, owner_id, title, source_run_id, created_at, updated_at)` 强制 owner 隔离    |
| CR3 | 前端：路由 + 越权防护          | `/creator/canvas/[appId]`；服务端 + 客户端双重校验 app 属于当前 tenant                                |
| CR4 | 前端：runtime 模式 + 事件流    | 画布加 `runtimeMode`、状态机 pending/running/succeeded/paused、订阅 SSE 渐进添加节点                  |
| CR5 | 前端：底部输入框 + slash 占位  | 圆角、文件上传、@/ 触发空 menu                                                                         |
| CR6 | 前端：暂停节点的行内交互       | 「继续」/「编辑后继续」(M6 modal)；Human Input 节点走原表单                                            |
| CR7 | 前端：保存 + 我的画布列表页    | 工具栏保存 → 命名对话框；`/creator/canvas` 列表，点击重现                                              |
| CR8 | 整体复审                       | Codex CLI 仍故障则手动 review                                                                          |

## 后端设计

### CR1 — 节点级暂停 + resume

**暂停**：在 chatflow 引擎处理 `node_finished` 事件后，检查 `node.data.allow_user_edit_input` 或 `allow_user_edit_output`。若任一为 true：
- 不下发该节点的下游 `node_started`
- 把 workflow_run.status 改为 `paused`
- 推送一个 `workflow_paused` SSE 事件携带 `node_id` + `kind`

**resume endpoint**:
```
POST /apps/<app_id>/messages/<message_id>/resume-from/<node_id>
body: { kind: "input"|"output", overrides_just_saved?: bool }
```
- 检查 workflow_run.status == "paused" 且 paused_at_node_id == node_id（防止误恢复）
- 调 `WorkflowRerunService.prepare(rewind=node_id, kind)` 拿 plan
- 调 `WorkflowRerunService.dispatch(plan)` 走 M7 路径继续

**与 M7 stub 的关系**：CR1 实际让 dispatch 不再是 stub —— 它需要把 chatflow generator 接入。这是 M7 follow-up 的实质性落地。

### CR2 — user_canvases

```sql
CREATE TABLE user_canvases (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  app_id UUID NOT NULL,
  owner_id UUID NOT NULL,
  title VARCHAR(200) NOT NULL,
  source_run_id UUID NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_user_canvases_owner ON user_canvases(owner_id, created_at DESC);
CREATE INDEX ix_user_canvases_tenant_app ON user_canvases(tenant_id, app_id);
```

**Endpoints**:
- `GET /creator/canvases?app_id=` 列当前 user 的画布
- `POST /creator/canvases` body=`{app_id, title, source_run_id}` 创建
- `GET /creator/canvases/<id>` 取详情
- `PATCH /creator/canvases/<id>` 改名
- `DELETE /creator/canvases/<id>`

所有 endpoint 强制 `owner_id == current_user.id`，后端无视前端传的 owner。

## 前端设计

### CR3 — 路由

```
web/app/creator/canvas/page.tsx              → 我的画布列表
web/app/creator/canvas/[appId]/page.tsx      → 运行时画布
web/app/creator/canvas/[appId]/[canvasId]/   → 重现已保存画布
```

进入后 client 校验：调 `/apps/<id>` 失败（403/404）→ 跳回 `/creator`。
`_CREATOR_ALLOWED_PREFIXES` 加上 `/console/api/creator/canvases` 和 `/console/api/apps/<id>/resume-from/`。

### CR4 — 画布 runtime 组件（fork）

新建 `web/app/components/canvas-runtime/`，从 `web/app/components/workflow/` 复制必要的：
- ReactFlow 容器组件（去掉所有侧栏、操作栏、面板挂点）
- 节点渲染壳（保留 `BlockEnum` 路由到节点类型，节点配置文件直接 import 自 `workflow/nodes/<type>/`，避免内容层 fork）
- 边渲染（先复用同款样式，后续改）

新增 runtime 专属能力：
- 节点 visibility 受 `runtimeNodeStates` 控制：未到达节点 `display: none`
- 节点状态徽章：`pending` 不显示、`running` 蓝色脉冲、`succeeded` 绿✓、`failed` 红✗、`paused-for-edit` 橙色边框 + CTA
- 整个画布强制只读（删/拖/连边 全禁用）
- 工具栏：保存 + minimap + fit-view + 缩放（自带）

后续改样式（圆角、阴影、动效）只动 `canvas-runtime/`，不影响后台工作流画布。

新建 `web/app/creator/canvas/[appId]/runtime-store.ts` (zustand)：
```ts
interface RuntimeState {
  nodeStates: Record<string, 'pending' | 'running' | 'succeeded' | 'failed' | 'paused'>
  pausedNodeId: string | null
  pausedKind: 'input' | 'output' | 'human-input' | null
  applyEvent(event: WorkflowSSEEvent): void
}
```

### CR5 — 输入框

`web/app/creator/canvas/[appId]/runtime-input.tsx`：
- 圆角，绝对定位 `bottom: 24px; left: 50%`
- 集成现有 `FileUploaderInChatInput`
- 监听 `@` 和 `/` keydown → 显示空 popover（CR5 只占位，后续接素材库 / 提示词库 API）
- 提交 → 调 chatflow `chat-messages` SSE，事件路由到 runtime-store

### CR6 — 暂停节点 UI

复用 `RerunOverrideModal` (M6)；在画布节点 portal 一个小工具条：
- `[继续]` → POST `resume-from/<node_id>?kind=input`，无 override
- `[编辑后继续]` → 打开 modal，保存后端会自动 resume（M6 + CR1 联动）

### CR7 — 保存

工具栏 `[保存为画布]` 按钮 → AlertDialog 提示输入标题 → POST `/creator/canvases` body=`{app_id, title, source_run_id}`。

`/creator/canvas` 列表页：网格卡片，每卡显示标题 + 创建时间 + 节点数（来自 source_run_id 关联的 workflow_node_executions count）。点击进 `/creator/canvas/[appId]/[canvasId]`，画布按 source_run_id 一次性 replay 所有 `node_finished`。

## 风险与权衡

1. **CR1 引擎暂停是真正困难的部分**。chatflow 现有 generator 没有「暂停后再恢复」的能力（除了 Human Input）。可能要改 PipelineRunner 或包一层 supervisor。如果时间不够，CR1 退化方案：暂停 = 直接结束当前 run + 标记 source_run_id；继续 = 调 M7 dispatch 重头跑（祖先 reuse 不计费）。
2. **CR4 节点位置抖动**。空画布逐个加节点会触发 ReactFlow auto-layout 重排。方案：第一个 `node_started` 时一次性把整个 graph 节点都建出来（pending 状态、display:none），后续状态切换不重排。
3. **重现快照与画布编辑的脏数据**。如果工作流模板被管理员改了再打开旧画布，节点 ID 可能对不上。方案：source_run_id 存了 workflow snapshot 的话直接读快照而不是 latest workflow。需查 chatflow 是否有 workflow_snapshot。
4. **越权**：路由 prefix `/console/api/creator/canvases` 已在白名单内（已审），但 resume-from 的 prefix 需要确认。

## Open questions

- 输入框文件上传：限定视频音频图片，还是开放？（默认按 chatflow 的 file_upload 配置走）
- 画布工具栏除了保存，还要哪些？（fit-view、minimap toggle、缩放可以默认有）
- 列表页：先做按时间排，再考虑搜索 / tag

---

写完，等你 review。如果方向 OK 就开 CR1，如果某个里程碑想拆/合/换顺序也现在说。
