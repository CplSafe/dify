# 素材库前端 — GPT 交接文档

> **目的**：把 dify-zd 分支上素材库前端剩余 18 个 task（Task 3-20）交接给 GPT 继续做。前面 brainstorm + 后端 + 前端 plan 全部由 Claude 完成；上下文不够了，前端实施换 GPT。

**交付时点**：2026-04-29
**当前 git HEAD**: `eb0b02852` on branch `dify-zd`
**剩余工时估计**: 4-5 天

---

## 1. 你（GPT）需要立刻读的 3 份文档

按顺序读，全是已落库的设计/计划，**不要重做 brainstorm**：

1. **后端设计** `docs/plans/2026-04-28-asset-library-design.md` — 后端 API 形状、数据模型、错误码（已实现，HEAD `37ab43022`）
2. **前端设计** `docs/plans/2026-04-29-asset-library-frontend-design.md` — 12 节，含组件清单、状态分布、i18n、测试策略、风险清单
3. **前端实施计划** `docs/plans/2026-04-29-asset-library-frontend-plan.md` — **20 个 task 的可执行清单**，每个 task 有完整的代码块、测试代码、验证命令、commit message。**这是你的主工作清单。**

---

## 2. 当前进度

| Task | 状态 | Commit |
|---|---|---|
| 1 — oRPC contracts (`web/contract/console/asset-library.ts`) | ✅ DONE | `eb0b02852` |
| 2 — Router registration (`web/contract/router.ts`) | ✅ DONE | `eb0b02852`（合并提交） |
| **3-20** | ⏳ TODO | — |

**已 push 到 origin/dify-zd 的最后 commit：** `eb0b02852`（用 `git log origin/dify-zd..HEAD` 验证你的本地是否需要 push）

---

## 3. 项目环境与硬约束

### 3.1 工作目录

```
/Users/guijinhao/Documents/zhongda/dify
```

后端在 `/api`（Python Flask + uv），前端在 `/web`（Next.js + pnpm）。**只动 `/web`，后端别碰。**

### 3.2 分支

`dify-zd`（**不要建 worktree，不要切 main**）。直接在 `dify-zd` 上 commit。

### 3.3 必读 CLAUDE.md / AGENTS.md

- 项目根 `CLAUDE.md` — 顶层约束
- `web/CLAUDE.md` — 前端硬约束（关键内容下面 §3.4 摘录）
- `web/docs/test.md` — 测试规范（**mandatory**）
- `web/docs/lint.md` — lint 规范
- `web/docs/overlay-migration.md` — overlay 组件迁移规则（**mandatory**）

### 3.4 web/CLAUDE.md 关键约束（必须遵守）

> ### Overlay Components (Mandatory)
> - 在新代码或修改的代码中只使用 `@/app/components/base/ui/*` 下的 overlay primitives
> - 不要从 `@/app/components/base/*` 引入已废弃的 overlay；触碰旧代码时优先迁移
>
> ### Query & Mutation (Mandatory)
> - `frontend-query-mutation` skill 是 source of truth — TanStack Query + oRPC 的契约/调用/失效/错误处理
>
> ### Automated Test Generation
> - 使用 `web/docs/test.md` 作为测试生成的规范
> - 所有前端测试必须符合 `frontend-testing` skill（mandatory）
>
> ### i18n
> - User-facing 字符串必须用 `web/i18n/en-US/`，**不要硬编码中英文文案**

### 3.5 工具命令

```bash
# 在 web/ 目录下
pnpm vitest run <file>            # 跑单测
pnpm vitest run --coverage <...>  # 带覆盖率
pnpm lint:fix <file>              # 修 lint
pnpm type-check:tsgo              # 类型检查
pnpm run knip                     # 死代码检查（pre-commit hook 也跑）
pnpm dev                          # 开发服务器（Task 8 / Task 20 手测时用）
```

**重要**：本项目有 **pre-commit hook 跑 knip**。如果某个文件没被任何地方 import，commit 会失败。**Task 1 就被这个卡住** —— 解决方式是 Task 1+2 合并提交（contract 创建 + router 注册同时上）。后续 task 注意：**先创建被引用的工具/类型，紧接着创建消费者，单独 commit 文件不要让它"孤儿"超过一个 commit**。

---

## 4. 已识别但 plan 没写清楚的隐藏陷阱

### 4.1 PostToolUse Prettier 钩子会反复改格式

用户级 `~/.claude/auto-simplify.sh` PostToolUse 钩子会把刚写的文件用 prettier 重写（改成双引号 + 分号），跟项目 ESLint 规则（单引号 + 无分号）冲突。**对策**：每次写完文件都跑 `pnpm lint:fix <file>` 把它扳回项目风格。

### 4.2 i18n resources.ts 是 source of truth

注册新 namespace 必须在 `web/i18n-config/resources.ts` 里加 import + Resources 类型字段（**Task 6 已写明**）。先前 social-publish 漏过这一步，类型不报错但 runtime 缺 namespace。

### 4.3 oRPC 的 client 命名空间访问路径

正确：`consoleClient.assetLibrary.list({ query })` / `consoleQuery.assetLibrary.list.queryKey({ input: { query } })` / `consoleQuery.assetLibrary.list.key()` — 跟 `web/service/use-billing.ts` 完全一致。**Task 4 实施时务必先读 `use-billing.ts` 验证 `key()` vs `queryKey()` 的具体调用形式。**

### 4.4 文件上传不走 oRPC

multipart 必须走 `web/service/base.ts` 的 `upload()` helper（XMLHttpRequest，支持进度）。**Task 3 已写明，不要尝试用 oRPC contract 表达 multipart**。

### 4.5 Toast 和 Modal 的 import 路径

Plan 里写了 `import Toast from '@/app/components/base/toast'`，**这个路径要先验证**（subagent 在 Task 14 实施前要去 grep 一个现有 component 比如 `social-publish` 里怎么 import 的，复用同样的路径）。Modal 同理 — **必须用 `@/app/components/base/ui/*` 的 overlay primitive**，不要写 inline `<div className="fixed inset-0">`（plan 里 Task 15 留了 inline 作为 fallback，**实施时要替换成项目原语**）。

### 4.6 Drawer primitive

Task 17 的右侧 drawer，**先 grep 项目里现有 drawer**（比如 `web/app/components/datasets/.../drawer.tsx` 或 `web/app/components/creator/social-publish/publish-drawer.tsx`）复用，不要从零写。

---

## 5. 推荐的执行节奏

Plan 里 20 个 task 已经按 6 个 phase 组织好。**每个 phase 结束跑一次完整 lint + type-check + 全部相关测试**，确保上一阶段没破东西。

| Phase | Tasks | 关键产出 | 验证 |
|---|---|---|---|
| 1 契约 + Service | 1-4 | contract / service / hooks | `vitest run service/` 全过 |
| 2 i18n + sidebar + 入口 | 5-8 | i18n bundle / sidebar 入口 / page.tsx | `pnpm dev` 看 sidebar 出现"素材库"项 |
| 3 基础组件 | 9-13 | tabs/filterbar/pagination/grid/list | 各组件单测全过 |
| 4 上传 + 提示词 | 14-15 | UploadDropzone / PromptDialog | 各组件单测全过 |
| 5 详情 drawer | 16-17 | DeleteConfirmDialog / AssetDetailDrawer | 各组件单测全过 |
| 6 组装 + 验收 | 18-20 | AssetLibraryPage 组装 / 全套验收 | 总覆盖 ≥ 80%，手测 10 步全过 |

**每完成一个 task 就 commit**，message 用 plan 里指定的格式 `feat(asset-library/web): <task name>`。

---

## 6. TDD 节奏（每个 task 都是这样）

```
1. 写失败的测试（红）
2. 跑测试，看到 FAIL（确认是真红，不是测试本身写错）
3. 写最小实现（绿）
4. 跑测试，看到 PASS
5. pnpm lint:fix <files>
6. pnpm type-check:tsgo
7. git add <files> && git commit -m "..."
```

**这个节奏 plan 里每个 task 都明确写了，跟着做就行。**

---

## 7. 风险与回滚

### 7.1 如果 commit 被 knip 拦

某个文件还没被引用 → 把消费它的下一个 task 一起做，单 commit 提交两个文件。

### 7.2 如果 type-check 失败但你不确定原因

不要硬改类型，先停下汇报。Plan 第 §7 风险清单里列了已知风险（contract 路径不匹配、signed_url 返回 null 等）。

### 7.3 如果 oRPC client 类型解析不到 `assetLibrary.list`

Task 2 的 router.ts 注册检查一下 namespace 名称（必须是 `assetLibrary`，对应 `consoleClient.assetLibrary.list`）。当前 Task 2 已 PASS，不应该出。

### 7.4 如果某个测试一直绿不了

把具体失败贴出来，**不要跳过测试**（不要写 `.skip` 或注释掉）。

---

## 8. 你（GPT）开始时立刻做的 3 件事

1. `cd /Users/guijinhao/Documents/zhongda/dify` 然后 `git pull origin dify-zd`
2. 完整读完 §1 列的 3 份文档（特别是 plan 里 Task 3 开始）
3. 确认本地 `web/contract/console/asset-library.ts` 和 `web/contract/router.ts` 的状态（Task 1+2 已完成 commit `eb0b02852`），开始 Task 3

---

## 9. 当前 16 个剩余 task 概要

| Task | 文件 | 主要内容 |
|---|---|---|
| 3 | `web/service/asset-library.ts` + spec | uploadAssetFile (multipart) |
| 4 | `web/service/use-asset-library.ts` + spec | 6 个 TanStack Query hooks |
| 5 | `web/i18n/{en-US,zh-Hans}/asset-library.json` | i18n bundle |
| 6 | `web/i18n-config/resources.ts` | 注册 namespace |
| 7 | `web/app/components/creator/sidebar.tsx` | 加导航项 |
| 8 | `web/app/(creatorLayout)/creator-asset-library/page.tsx` + placeholder | 入口 stub |
| 9 | `_components/asset-tabs.tsx` + spec | 5 个 tab 组件 |
| 10 | `_components/asset-filter-bar.tsx` + spec | 搜索 + category + tags chips |
| 11 | `_components/pagination.tsx` + spec | 分页 |
| 12 | `_components/{asset-card,asset-grid}.tsx` + spec | 网格形态（图/视频） |
| 13 | `_components/{asset-row,asset-list}.tsx` + spec | 表格形态（音频/提示词） |
| 14 | `_components/upload-dropzone.tsx` + spec | 拖拽上传 + 多文件并发 + 进度 chip |
| 15 | `_components/prompt-dialog.tsx` + spec | 提示词创建 dialog + variable 动态表 |
| 16 | `_components/delete-confirm-dialog.tsx` + spec | 删除确认 |
| 17 | `_components/asset-detail-drawer.tsx` + `asset-preview.tsx` + spec | 右侧 drawer + 4 种预览 + 编辑 |
| 18 | `_components/asset-library-page.tsx` | 顶层组装 |
| 19 | — | 跑全套测试 + 覆盖率 + lint + type-check |
| 20 | — | 手测交给用户跑（10 步清单见 plan §Task 20） |

每个 task 在 plan 文档里都有完整代码 + 测试 + 验证命令。**plan 是你的主工作 manual。**

---

## 10. 完成标准

- 全部 20 个 task 完成
- `pnpm vitest run` 全过，新模块覆盖 ≥ 80%
- `pnpm lint:fix` 干净
- `pnpm type-check:tsgo` 0 errors
- 用户跑 plan §Task 20 的 10 步手测全过
- `git push origin dify-zd` 成功

---

## 11. 联系方式

如果遇到 plan 没覆盖的情况（比如某个 Dify primitive 找不到、某条假设错了），**停下来汇报，不要硬猜**。用户会切回 Claude 上下文澄清。
