# P8: 社交发布账号成员级隔离

**日期**：2026-04-19
**前置**：P1-P7（社交发布全链路）
**预估工作量**：约 5h

## 背景

当前实现把社交发布账号绑在 `tenant_id`（工作空间 ID）上：

```python
def list_by_tenant(self, tenant_id, ...):
    return ...where(SocialPublishAccount.tenant_id == tenant_id)
```

**问题**：所有者绑了一个抖音号，**空间内所有成员都能看到/使用**。但抖音号是个人资产：
- 每个成员有自己的抖音号
- 一个成员发布到另一个成员的号会触发抖音风控（cookie 被多设备使用）
- 成员之间不应能看到/操作彼此的号

**用户原话**：「抖音每个人都不一样 不能空间级别」

## 决策

**账号绑定从「空间级」改成「成员级」**：
- 每个 `social_publish_accounts` 行已有 `created_by` 字段（绑号时记录的用户 ID）
- 改 `list_by_tenant_and_user(tenant_id, user_id)` 用 `WHERE tenant_id = ? AND created_by = ?` 双过滤
- single-flight 锁的 key 加 `user_id` 维度，使「不同成员的号」可以并发
- task 行写入时记录 `created_by`，发布任务的 has_active_for_account 也按用户过滤

## 不需要做的

- ❌ DB 迁移 backfill：`created_by` 字段从 P1 就有，每行都有真实值
- ❌ 加 visibility 字段做「私有/共享」二选一：你明确要「每个人都不一样」
- ❌ 改 tier.concurrent / tier.max_pending：那是租户层并发，跟成员隔离正交
- ❌ 改 sau worker 端：worker 只认 `cookie_path`，路径已经按 `tenant_<id>/<platform>/<sau_account_id>.json` 隔离，不需要再按 user 嵌一层

## 改动范围

### 仓库层（`api/repositories/sqlalchemy_social_publish_account_repository.py`）

```python
# 新方法
def list_by_tenant_and_user(self, tenant_id, user_id, *, platform=None) -> list[Account]:
    """成员只能看到自己绑的号。Admin 想看全部走 list_by_tenant。"""
    return ...where(tenant_id == ?, created_by == ?, ...)

# 加复合索引加速
sa.Index("social_publish_account_tenant_user_platform_idx",
         "tenant_id", "created_by", "platform"),
```

任务仓库 (`sqlalchemy_social_publish_task_repository.py`):
```python
# 改方法签名
def has_active_for_account(self, *, tenant_id, account_id, user_id) -> bool:
    return ...where(tenant_id == ?, account_id == ?, created_by == ?, ...)
```

`count_active_for_tenant` 不动 — 它服务于 P3 的 tier quota，是租户层指标。

### 服务层（`api/services/social_publish_service.py` + `social_publish_task_service.py`）

```python
# SocialPublishService
def list_accounts(self, *, tenant_id, user_id, platform=None):
    return self._repo.list_by_tenant_and_user(tenant_id, user_id, platform=platform)

def get_account(self, *, account_id, tenant_id, user_id):
    # 加 user_id 过滤 — 防止用户 B 拿到用户 A 账号的 id 后伪造请求
    row = self._repo.get_by_id_and_tenant_and_user(account_id, tenant_id, user_id)
    if row is None:
        raise AccountNotFoundError(...)  # 故意 404 不暴露存在性

def delete_account(self, *, account_id, tenant_id, user_id):
    # 同上：用户 B 不能 DELETE 用户 A 的号
```

```python
# SocialPublishTaskService
def _single_flight_lock_key(tenant_id, user_id, account_id):
    return f"sau:publish:single_flight:{tenant_id}:{user_id}:{account_id}"
    #                                              ^^^ 新加 user_id 维度

def create_task(self, *, tenant_id, created_by, request):
    # account 已经是 user_id-scoped 取出来的，所以
    # has_active_for_account 同样 user_id-scoped
```

### 控制器层（`api/controllers/console/social_publish/{accounts,tasks}.py`）

只是参数透传，无逻辑变化：

```python
def get(self):
    current_user, current_tenant_id = current_account_with_tenant()
    accounts = service.list_accounts(
        tenant_id=current_tenant_id,
        user_id=current_user.id,  # 新加
        platform=platform,
    )
```

### Alembic 迁移

只加索引，无数据变更：

```python
op.create_index(
    "social_publish_account_tenant_user_platform_idx",
    "social_publish_accounts",
    ["tenant_id", "created_by", "platform"],
)
```

### 前端

**不需要改**：
- 账号列表 API 返回的还是「我能看到的号」，FE 渲染逻辑没变
- 发布弹窗用的也是同一个 list API
- delete / re-auth 按钮调用同一个 API

可能需要的小调整（不阻塞）：
- 模态框副标题从「管理你绑定的抖音/小红书账号」可以改成「管理你的社交账号」（更明确「我的」）

## 安全性考量

新加的 user_id 过滤是个**额外**约束，不会让原本能访问的资源不可访问：
- 原来 user A 能看到 (tenant=X) 的所有号 → 现在 user A 只能看到自己绑的号
- 跨租户隔离仍然完整（tenant_id 仍然 WHERE）
- **没有新增权限放宽**

故意把 `get_by_id_and_tenant_and_user` 在找不到时抛 `AccountNotFoundError` 而不是 `PermissionDeniedError`：
- 防止暴露「这个 ID 在系统里存在但不是你的」
- 攻击者无法用枚举判断别人有没有号

## 测试策略

```python
def test_user_b_cannot_see_user_a_account(...):
    # A 绑号 → service.list_accounts(tenant=X, user=A) 返回 1 行
    # B 调用 service.list_accounts(tenant=X, user=B) 返回 0 行

def test_user_b_cannot_create_task_with_user_a_account(...):
    # A 绑了 account=acc-1
    # B 调用 service.create_task(account_id=acc-1, ...) 抛 AccountNotFoundError

def test_same_account_same_user_blocks_concurrent(...):
    # A 提一个发布 → 立刻提第二个 → 第二个抛 TaskAlreadyInFlightError

def test_same_tenant_different_user_can_concurrent(...):
    # A 用 acc-A 发布 + B 用 acc-B 发布 → 两个都成功
    # 验证 single-flight 锁不互相阻塞
```

## 工作量分解

| 子任务 | 估时 |
|---|---|
| 设计文档 | 0.5h |
| 仓库层方法 + 索引 + 单测 | 1h |
| 服务层 user_id threading + 单测 | 1.5h |
| 控制器透传 + 单测 | 0.5h |
| Alembic 迁移 | 0.3h |
| codex review | 0.5h |
| 实测 + commit + commit message | 0.7h |
| **小计** | **~5h** |

## 提交计划

3 个 commit：
1. `feat(social-publish): backend P8 — per-member account isolation`（一锅端：repo + service + controller）
2. `feat(social-publish): add Alembic migration for tenant+user+platform index`
3. （如果需要）`refactor(social-publish): minor i18n tweaks for "我的账号"`

## 不解决的事（YAGNI）

- **共享号回归**：将来真有运营团队需要共享号，再加 `visibility=shared|private` 字段，不在 P8 范围
- **管理员看全部**：admin 用户应不应该能看到全空间所有号？现在不做。要做也是后台管理面板的事（P6 设计文档里）
- **跨成员转移号**：用户 A 把号转给用户 B 的功能。罕见，P8 不做
