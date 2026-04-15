# 邀请 + 返点功能 UI 临时隐藏说明

**日期**: 2026-04-15
**分支**: `dify-zd`
**决定方**: 产品

## 背景

注册赠送 50 元体验额度上线后，产品决定暂时不对 C 端用户开放"邀请码 + 返点"功能的入口。
为了保留后续放开的可能，代码只在 UI 层做隐藏，后端能力完整保留。

## 当前状态

### 前端已隐藏（本次改动）

| 位置 | 文件 | 隐藏方式 |
|------|------|----------|
| 注册页"邀请码（选填）"输入框 | `web/app/signup/page.tsx` | 整块 JSX 删除；仍从 URL query 读取 `invite_code` 透传给后续步骤（分享链接流程不受影响） |
| 创作设置弹窗"邀请管理" tab | `web/app/components/creator/settings/creator-settings-modal.tsx` | `MENU_ITEMS` 里加 `hidden: true`；`InvitationTab` 组件和路由分支都保留 |
| 创作设置弹窗"返点账单" tab | 同上 | 同上：`rebate` 菜单项加 `hidden: true`；`RebateTab` 组件和路由分支都保留 |
| 创作页左下角余额徽章 | `web/app/components/creator/user-menu.tsx` | 移除 `/creator/balance` fetch 与金额展示；余额仅在"余额账单"tab 内可见 |

### 前端保留（未动）

- `web/app/components/creator/settings/tabs/invitation-tab.tsx`：邀请管理 tab 组件本体
- `web/app/components/creator/settings/tabs/rebate-tab.tsx`：返点账单 tab 组件本体
- `web/service/use-common.ts` 里 `MailRegisterPayload.invite_code`：邮箱注册 mutation 仍接受该字段
- `web/app/signup/set-password/page.tsx`：从 URL 读 `invite_code` 并传给 `useMailRegister`
- 分享链接 `/signup?invite_code=XXX` 自动绑定流程

### 后端完整保留

| 模块 | 路径 | 说明 |
|------|------|------|
| 邀请码绑定服务 | `api/services/invitation_service.py` | `bind_invitation_on_register` 事务化绑定 |
| 邮箱注册 | `api/controllers/console/auth/email_register.py` | 仍接受 `invite_code` 参数并调用 `bind_invitation_on_register` |
| 邀请管理接口 | `api/controllers/console/creator/invitation.py` | 创建/列表/撤销邀请码 |
| 返点配置 | `api/controllers/console/creator/rebate.py` | 超管读写 `RebateConfig`（rate/cost/freeze_days/settlement_hour/is_enabled） |
| 返点记录 | `api/controllers/console/creator/rebate.py` | 用户查自己的返点账单 + 超管作废待结算记录 |
| 返点结算/解冻定时任务 | `api/schedule/rebate_settlement_task.py`、`api/schedule/rebate_unfreeze_task.py` | Celery beat 按 `RebateConfig.settlement_hour` 执行；`is_enabled=false` 时整个任务 no-op |
| 数据表 | `AccountInvitation`、`RebateRecord`、`RebateConfig`、`UserBalance.rebate_pending` | 未删除，迁移已上线（`f8a1c2b3d4e5_add_rebate_freeze_unfreeze`） |

### 数据库状态

- 当前 head: `f8a1c2b3d4e5`（add rebate freeze/unfreeze support）
- **这个 migration 必须跑**：没跑的话，`rebate_records.status` / `unfrozen_at` 不存在，
  `/creator/rebate/records`、`rebate_settlement_task`、`RebateRecordCancelApi` 都会 500。
  本次上线已执行：`uv run flask db upgrade`。

### 推荐的运营期配置

产品决定暂停期间，建议超管把返点功能整体关闭以避免 Celery beat 把数据写进还未启用的
业务流程：

```http
PUT /console/api/creator/admin/rebate/config
{ "is_enabled": false }
```

`rebate_settlement_task` / `rebate_unfreeze_task` 在 `is_enabled=false` 时会立即 return
（见两个 task 的第一行守卫），不产生任何返点记录。数据表照常存在，便于日后重启。

## 恢复步骤

未来产品决定重新开放时，只需做以下几步：

1. **恢复注册页邀请码输入框**
   `web/app/signup/page.tsx` 把之前的 `<Input id="invite_code" ...>` 块加回来；
   参考 git 历史 commit `143badfe4` 的原版本。

2. **恢复"邀请管理" tab**
   `web/app/components/creator/settings/creator-settings-modal.tsx`
   把 `invitation` 菜单项的 `hidden: true` 删掉即可。

3. **恢复"返点账单" tab**
   同一文件，把 `rebate` 菜单项的 `hidden: true` 删掉。

4. **（可选）恢复左下角余额徽章**
   见 `user-menu.tsx` 顶部注释，把 `loadBalance` 逻辑加回来。
   余额显示是独立改动，和邀请/返点无强耦合，单独评估。

5. **重新开启返点总开关**
   `PUT /creator/admin/rebate/config { "is_enabled": true }`，
   并根据业务核对 `rebate_rate`、`cost_rate`、`freeze_days`、`settlement_hour`。

## 相关 commit

- `143badfe4` fix(invitation): bind invite code atomically during registration
- `31e829d24` feat(rebate): freeze pending rebate then unfreeze after configured days
- `c7338b527` feat(creator): hide owner-only settings tabs from members
- `3bbd0f440` feat(creator): hide invitation UI + balance badge; show signup bonus

## 注意事项

- **不要**因为前端隐藏了 UI，就去删后端路由、服务、模型或数据表。后端被定时任务、
  超管后台、单元测试多处依赖。
- **不要**把 `InvitationTab` / `RebateTab` 组件和 `invite_code` 相关的 payload 字段
  清理掉，属于"未使用但保留"的状态（knip 可能会报 unused exports，忽略）。
- **不要**跳过 `f8a1c2b3d4e5` 这个 migration。即使 UI 关闭了返点，数据库也必须和
  模型字段保持一致，否则任何触碰 `RebateRecord.status` 的代码路径（管理后台、
  定时任务启动时读 `RebateConfig`、作废接口）都会 500。
- 分享链接 `/signup?invite_code=XXX` 进入的用户仍会正常绑定邀请关系，这是产品
  决定的保留行为，属于"隐藏入口但不关闭能力"。
