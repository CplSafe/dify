# P5: 删除快手 + 位置真集成

**日期**：2026-04-19
**前置**：P4（multi-platform 发布 + 位置 desc-footer 妥协）
**预估工作量**：约 6h

## 背景

P4 完成时遗留两笔账：

1. **快手**：上游 `social-auto-upload` 没有 `ks_cookie_gen`，账号添加流程走不通。
   P4 用「FE 不让加 ks 账号 + `/login` 返回 400」绕开了，但发布通道还在
   `SUPPORTED_PLATFORMS_P2 = (douyin, xhs, ks)` 里挂着，是个不完整状态。

2. **位置**：用户填的 `location` 被 `apply_location_into_desc()` 拼成
   `📍 上海` 塞进 desc 末尾，**抖音/小红书后台没真正标记 POI**。
   原因是上游 uploader 的 `set_location()` 方法存在但没接进 `upload()`。

P5 把这两笔都还掉。

## 决策

**Q1：现有 KS 数据怎么处理？**
- ✅ 在 Alembic 迁移里清掉 `social_publish_account.platform = 'ks'` 行
  和对应的 `social_publish_task` 行
- 现状几乎没人加过 ks 账号（FE 早就不显示），实际是 no-op，但写迁移是
  把契约钉死的方式

**Q2：上游 patch 怎么处理？**
- ✅ 只在我们 fork 里 patch，不提上游 PR
- 用户已确认。优点：实施最快；代价：以后 sync 上游需要手动处理冲突
- 把改动集中在两个 uploader 文件里，sync 时差异容易识别

## 改动范围

### social-auto-upload（fork）

#### 删 KS

- `apps/sau_worker/_publish_runner.py`
  - 删掉 `_import_ks()` 和 `KS = PlatformBinding(...)` 实例
  - `PlatformName` Literal 从 `("douyin", "xhs", "ks")` 改 `("douyin", "xhs")`
  - `resolve_cookie_path` 的 `platform` 校验集合同步
- `apps/sau_worker/tasks/publish_ks.py` — **整个文件删**
- `apps/sau_api/routers/login_sse.py` — `_PLATFORM_LOGIN_SUPPORT` 删 `"ks": None`
- `apps/sau_api/cookie_paths.py` — 如果 Platform Literal 包含 ks 同步删
- `tests/sau_api/test_publish_xhs_ks_tasks.py` — 删 `TestKsPublish` 类，
  剩余 xhs 测试改名为 `test_publish_xhs_task.py`
- 删 `sau_contracts` 里的 `PUBLISH_KS` / `PUBLISH_KS_QUEUE`（如果有）

#### Location 真集成

**抖音**（`uploader/douyin_uploader/main.py`）：
- `DouYinVideo.__init__` 加 `location: str | None = None` 参数，存为 `self.location`
- `upload()` 在 `set_thumbnail()` 之前插入 `await self.set_location(page, self.location or "")`
- `set_location()` 已有的 `if not location: return` 处理空值，所以可以无脑调

**小红书**（`uploader/xiaohongshu_uploader/main.py`）：
- `XiaoHongShuVideo.__init__` 加 `location: str | None = None`，存为 `self.location`
- `upload_video_content()` 第 535 行 `# await self.set_location(...)` 注释取消，
  改成 `if self.location: await self.set_location(page, self.location)`

**Runner 收尾**（`apps/sau_worker/_publish_runner.py`）：
- 删 `apply_location_into_desc()` 的 📍 hack
- 改成新 helper `apply_location_extras()`：从 `platform_payload["location"]` 取出
  字符串，返回 `(desc, {"location": location})`，让 `_run_publish_async` 把
  `location` 透传到 `video_cls(...)` 构造函数
- 单元测试更新：原来断言 `desc.endswith("📍 ...")`，改成断言 `extra_kwargs["location"]`

### dify api（backend）

- `services/social_publish_task_service.py`
  - `SUPPORTED_PLATFORMS_P2 = ("douyin", "xhs")`（删 ks）
  - `_PLATFORM_PAYLOAD_KEYS` 删 `ks: frozenset()` 项
- `services/social_publish_service.py`
  - `SUPPORTED_PLATFORMS_P1` 已经是 `(douyin, xhs)`，不变
- `models/social_publish.py`
  - `SocialPublishPlatform` 枚举**保留 KS**（数据库里枚举值不能轻易删，旧
    数据可能有，PostgreSQL 改 enum 麻烦）
  - 应用层不再生成 ks 行
- 新 Alembic 迁移 `2026_04_19_xxxx-remove_ks_social_publish_data.py`：
  - `DELETE FROM social_publish_task WHERE platform = 'ks'`
  - `DELETE FROM social_publish_account WHERE platform = 'ks'`
  - downgrade：no-op（无法恢复，写注释说明）
- 单元测试更新

### dify web（frontend）

- `app/components/creator/social-publish/publish-drawer.tsx`
  - `SUPPORTED_PLATFORMS` 从 `['douyin', 'xhs']` 不变（已正确）
  - `LOCATION_PLATFORMS` 不变
  - 检查是否有 ks 残留 case
- `i18n/{en-US,zh-Hans}/social-publish.json`
  - 保留 `platforms.ks` key（万一后端枚举里旧 ks 行被列出，FE 还能显示文案）
- `types/social-publish.ts`
  - `SocialPublishPlatform = 'douyin' | 'xhs' | 'ks'` 保留 ks（同枚举）

## 不做的事（YAGNI）

- 不删 `SocialPublishPlatform.KS` 枚举值（PostgreSQL enum 改起来麻烦，零收益）
- 不提上游 PR（用户决定，节省工作量）
- 不重构 `apply_platform_extras` 接口（虽然现在所有平台都用同一个
  helper，但留着 hook 形态以后加新平台特性时不用改框架）

## 测试策略

- sau：原 43 测试 → 删 KS 测试后约 41，加 location 集成测试约 +3
- dify backend：原 90 测试，更新平台名断言，加迁移测试约 +1
- dify FE：原 25 测试，断言 `platform_payload.location` 仍透传

## 风险

- **上游 sync 冲突**：以后从上游同步必然在 douyin/xhs uploader 文件冲突。
  缓解：commit 信息明确写 `feat(uploader): wire set_location into upload pipeline`，
  sync 时一眼能看出来。
- **set_location 选择器漂移**：抖音/小红书改前端会让 `set_location` 里的
  selector 过期。这是上游已存在的风险，P5 不引入新的脆弱性。

## 提交计划

3 个 commit：
1. `feat(sau): P5 — remove KS + wire real set_location into upload pipeline`
2. `feat(social-publish): backend P5 — remove KS support + cleanup migration`
3. `feat(social-publish): frontend P5 — drop KS-related UI strings`（如果有改）
