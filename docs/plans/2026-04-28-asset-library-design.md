# 素材库（Asset Library）设计文档

- **日期**: 2026-04-28
- **作者**: dify-zd 团队
- **状态**: 已确认（brainstorm 完成，待实施）
- **范围**: 后端实现（前端单独 brainstorm，不在本文档范围）

---

## 1. 背景与定位

素材库是租户级别的素材资产管理模块，用户可以上传 **图片 / 音频 / 视频**，以及创建并保存 **提示词**。下游消费方为 `creator_task` 与 `social_publish` 两个已有模块。

**关键定位：**

- 租户共享：同一 workspace 内成员都能查看/编辑/删除（仅展示 `created_by`，不做权限隔离）。
- 复用 Dify 已有 `FileService` + `upload_files` 表 + storage 抽象（local / S3 / OSS 全部沿用）。素材库本身只是"管理语义层"，不重复造文件存储。
- 不参与 workflow 节点引用（YAGNI 砍掉，未来如有需要单独再设计）。

---

## 2. 数据模型

### 2.1 新增表 `asset_libraries`

```python
# models/asset_library.py
class AssetLibrary(Base):
    __tablename__ = "asset_libraries"

    id: Mapped[str] = mapped_column(StringUUID, server_default=func.gen_random_uuid(), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)  # account_id

    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # 取值: 'image' | 'audio' | 'video' | 'prompt'

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    category: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # 文件类字段（提示词为 NULL）
    upload_file_id: Mapped[Optional[str]] = mapped_column(StringUUID)
    cover_url: Mapped[Optional[str]] = mapped_column(String(512))
    duration: Mapped[Optional[float]] = mapped_column(Float)        # 秒
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)

    # 提示词字段（文件类为 NULL）
    content: Mapped[Optional[str]] = mapped_column(Text)
    prompt_variables: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_asset_lib_tenant_type_created", "tenant_id", "asset_type", "created_at"),
    )
```

### 2.2 `prompt_variables` 结构示例

```json
[
  {"name": "product_name", "type": "string", "default": "", "description": "产品名"},
  {"name": "audience", "type": "string", "default": "年轻人"}
]
```

校验规则：

- `name` 必填，仅允许字母数字下划线
- `type` 必填，枚举 `string` / `number` / `boolean`
- `default` 可选，类型须与 `type` 匹配
- `description` 可选

### 2.3 Alembic 迁移

新增 `api/migrations/versions/xxxx_add_asset_libraries.py`，CREATE TABLE + 复合索引。**不外键关联** `upload_files.id`（沿用 Dify 现有惯例：`upload_files` 没有反向外键，避免耦合，由 service 层负责级联）。

---

## 3. 文件类型与限制

### 3.1 MIME 白名单（素材库自定义，比 Dify 全局更严）

| 类型 | 允许 MIME |
|---|---|
| 图片 | `image/jpeg`, `image/png`, `image/webp`, `image/gif` |
| 视频 | `video/mp4`, `video/quicktime` (mov) |
| 音频 | `audio/mpeg` (mp3), `audio/mp4` (m4a), `audio/wav` |
| 提示词 | 无（纯文本） |

后续若 social-publish 新增平台需要补格式，扩白名单即可。

### 3.2 大小限制

复用 Dify 现有全局环境变量，不新增配置：

- `UPLOAD_FILE_SIZE_LIMIT`（图片）
- `UPLOAD_AUDIO_FILE_SIZE_LIMIT`
- `UPLOAD_VIDEO_FILE_SIZE_LIMIT`

---

## 4. 部署依赖

### 4.1 系统二进制（需在部署环境/Docker 镜像中安装）

- **`ffmpeg`** —— 视频封面抽帧
- **`ffprobe`** —— 音视频时长 / 分辨率提取（随 ffmpeg 一起）

### 4.2 Python 依赖

- `Pillow` —— 图片宽高读取（Dify 已依赖）
- `mutagen` —— 音频元数据（**新增**到 `api/pyproject.toml`，`uv sync`）

---

## 5. Service 层设计

### 5.1 文件结构

```
api/
├── services/
│   ├── asset_library_service.py             # 主服务类（静态方法风格）
│   ├── asset_library/
│   │   └── metadata_extractor.py            # ffprobe / Pillow / mutagen 封装
│   └── errors/
│       └── asset_library.py                 # AssetLibraryError 等异常
└── models/
    └── asset_library.py
```

### 5.2 `AssetLibraryService` 接口

```python
class AssetLibraryService:
    # ===== 文件类（图/音/视频） =====
    @staticmethod
    def create_file_asset(
        tenant_id: str,
        user: Account,
        file: FileStorage,
        asset_type: Literal["image", "audio", "video"],
        name: str,
        description: str | None,
        tags: list[str],
        category: str | None,
    ) -> AssetLibrary:
        """
        1. MIME 白名单校验（按 asset_type 收紧）
        2. 调用 FileService.upload_file() 复用现有 storage 抽象
        3. 提取元数据：图片宽高 / 音视频 duration / 视频生成 cover_url
        4. 落库 AssetLibrary
        5. 任一步失败回滚（不留孤儿 upload_files / AssetLibrary 行）
        """

    # ===== 提示词类 =====
    @staticmethod
    def create_prompt_asset(
        tenant_id: str,
        user: Account,
        name: str,
        content: str,
        prompt_variables: list[dict],
        description: str | None,
        tags: list[str],
        category: str | None,
    ) -> AssetLibrary:
        """
        1. pydantic 校验 prompt_variables 结构
        2. 落库
        """

    # ===== 通用 =====
    @staticmethod
    def list_assets(
        tenant_id: str,
        asset_type: str | None = None,
        keyword: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> Pagination: ...

    @staticmethod
    def get_asset(tenant_id: str, asset_id: str) -> AssetLibrary: ...

    @staticmethod
    def update_asset_metadata(tenant_id: str, asset_id: str, **fields) -> AssetLibrary:
        """
        白名单可改字段: name / description / tags / category / content / prompt_variables
        黑名单（拒绝改）: asset_type / upload_file_id / file_size / duration / width / height
        """

    @staticmethod
    def delete_asset(tenant_id: str, asset_id: str) -> None:
        """
        文件类: 删 upload_files 行 + storage 物理文件 + AssetLibrary 行
        提示词: 仅删 AssetLibrary 行
        Storage 物理删除失败不阻塞 DB 删除（与 Dify FileService 风格一致）
        """
```

### 5.3 元数据提取（同步执行）

- **图片**：`Pillow.Image.open()` → `width` / `height`
- **音频**：`mutagen.File()` → `duration`
- **视频**：`ffprobe -v quiet -print_format json -show_streams` → `duration` / `width` / `height`
- **视频封面**：`ffmpeg -i <input> -ss 1 -vframes 1 <cover.jpg>` → 上传到 storage → `cover_url`

预期延迟 < 2 秒，同步执行不阻塞用户体验。后续如发现慢可迁 Celery（暂不做）。

---

## 6. HTTP API 设计

### 6.1 蓝图注册

```
api/controllers/console/asset_library/
├── __init__.py          # 蓝图注册，前缀 /console/api/asset-library
├── files.py             # 文件类素材
├── prompts.py           # 提示词类素材
└── assets.py            # 通用 CRUD（list / detail / update / delete）
```

所有端点装饰器三件套：`@setup_required` `@login_required` `@account_initialization_required`（与 datasets / apps 一致）。

### 6.2 端点清单

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/asset-library/files` | 创建文件类素材（multipart） |
| `POST` | `/asset-library/prompts` | 创建提示词素材（JSON） |
| `GET` | `/asset-library` | 统一列表（支持 type / keyword / tags / category 过滤 + 分页） |
| `GET` | `/asset-library/<asset_id>` | 详情 |
| `PATCH` | `/asset-library/<asset_id>` | 更新元数据 |
| `DELETE` | `/asset-library/<asset_id>` | 删除 |

### 6.3 请求/响应样例

**创建文件类（multipart）：**
```
POST /console/api/asset-library/files
Content-Type: multipart/form-data

file=<binary>
asset_type=video
name=产品介绍片
description=...
tags=["广告","产品"]
category=营销
```

**创建提示词（JSON）：**
```
POST /console/api/asset-library/prompts
Content-Type: application/json

{
  "name": "小红书种草模板",
  "content": "为 {{product_name}} 写一段面向 {{audience}} 的种草文案",
  "prompt_variables": [
    {"name": "product_name", "type": "string"},
    {"name": "audience", "type": "string", "default": "年轻人"}
  ],
  "tags": ["种草", "小红书"]
}
```

**列表响应：**
```json
{
  "data": [
    {
      "id": "...",
      "asset_type": "video",
      "name": "产品介绍片",
      "tags": ["广告","产品"],
      "category": "营销",
      "cover_url": "https://...signed",
      "duration": 15.2,
      "width": 1920,
      "height": 1080,
      "file_size": 5242880,
      "signed_url": "https://...signed",
      "created_by": {"id": "...", "name": "张三"},
      "created_at": "2026-04-28T..."
    }
  ],
  "total": 42,
  "page": 1,
  "limit": 20,
  "has_more": true
}
```

### 6.4 错误处理

`api/services/errors/asset_library.py`：

- `AssetLibraryError` 基类
- `UnsupportedMimeTypeError` → HTTP 400
- `InvalidPromptVariablesError` → HTTP 400
- `AssetNotFoundError` → HTTP 404
- `FileSizeLimitExceededError` → HTTP 413

### 6.5 序列化

`api/fields/asset_library_fields.py` 用 `flask_restful.fields.Nested` 定义 `asset_fields`：

- 文件类带 `signed_url`（通过 `FileService.preview_file_url` 生成临时签名 URL，不暴露 storage_key）
- 视频额外带 `cover_url`（同样为签名 URL）
- `created_by` 嵌套展开为 `{id, name, avatar?}`

---

## 7. 测试策略

遵循项目 TDD 约定（red → green → refactor），目标覆盖率 80%+。

### 7.1 测试文件

```
api/tests/unit_tests/
├── services/
│   └── test_asset_library_service.py
└── controllers/console/asset_library/
    ├── test_files_controller.py
    ├── test_prompts_controller.py
    └── test_assets_controller.py
```

### 7.2 Service 单测覆盖

**`create_file_asset`：**
- ✅ 各类型 MIME 白名单接受/拒绝（参数化 image/audio/video × 合法/非法）
- ✅ 元数据正确提取（mock ffprobe / Pillow / mutagen）
- ✅ 视频封面生成成功后写入 `cover_url`
- ✅ FileService 失败时事务回滚（不留孤儿 AssetLibrary 行）

**`create_prompt_asset`：**
- ✅ `prompt_variables` 合法结构通过
- ✅ 非法结构（缺 `name` / `type` 错）抛 `InvalidPromptVariablesError`

**`list_assets`：**
- ✅ tenant_id 隔离（A 租户看不到 B 租户的）
- ✅ keyword 匹配 name / description
- ✅ tags / category / type 三个过滤独立 + 组合
- ✅ 分页返回 `has_more`

**`update_asset_metadata`：**
- ✅ 白名单字段可改
- ✅ 黑名单字段（asset_type / upload_file_id 等）尝试改时被拒

**`delete_asset`：**
- ✅ 文件类：`upload_files` 行被删 + storage 物理文件被清理
- ✅ 提示词：只删 `AssetLibrary` 行
- ✅ 跨租户删除返回 404

### 7.3 Controller 单测覆盖

- 401（未登录）/ 403（未初始化账号）/ 404（跨租户访问）三件套
- multipart 上传、JSON 创建、PATCH 部分更新的 happy path
- 文件超过 `UPLOAD_VIDEO_FILE_SIZE_LIMIT` 返回 413

### 7.4 Fixture 复用

沿用 `api/tests/unit_tests/conftest.py` 现有的 `tenant` / `account` / `db_session`，新增 `asset_library_factory` 工厂。

---

## 8. 实施分阶段

### Phase 1：数据层（约半天）

1. 新增 `models/asset_library.py`
2. Alembic 迁移 `add_asset_libraries.py`
3. 本地 PostgreSQL 跑迁移验证

### Phase 2：Service 层（约 1 天）

4. `services/asset_library_service.py` 全部方法
5. `services/asset_library/metadata_extractor.py`
6. `services/errors/asset_library.py`
7. **TDD：单测先行**，service 单测红→绿
8. 新增依赖：`api/pyproject.toml` 加 `mutagen`，`uv sync`

### Phase 3：HTTP 层（约半天）

9. `controllers/console/asset_library/` 三个 controller + 蓝图注册
10. `fields/asset_library_fields.py` 序列化
11. controller 单测红→绿

### Phase 4：后端验收

12. `uv run --project api pytest api/tests/unit_tests/...asset_library...` 全绿
13. 手测：curl 跑 happy path + 边界（MIME 拒绝、超限、跨租户）
14. **后端验收完毕，等用户确认后进入 Phase 5**

### Phase 5：前端

后端验收通过后，单独开一次 brainstorm 设计前端界面（不在本文档范围）。

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| ffmpeg 二进制需部署 | 部署门槛 | 本文档"部署依赖"章节明确标注，docker 镜像安装 |
| 视频封面抽帧耗时 | 上传请求阻塞 | Phase 2 内同步抽帧（预期 < 2s）；后续若慢再迁 Celery |
| 跨租户数据泄漏 | 严重安全问题 | 所有 service 方法首参强制 `tenant_id`；每个端点都有跨租户测试用例 |
| 删除时 storage 物理文件清理失败 | 孤儿文件占空间 | service 层 try/except 记录日志；不阻塞 DB 行删除（与 Dify `FileService.delete` 一致） |

---

## 10. 不在本次范围（YAGNI）

- ❌ 提示词版本管理 / 历史回滚
- ❌ 提示词被 workflow / chatflow 节点直接引用
- ❌ 跨租户素材共享 / 公共素材库
- ❌ 上传人级别的权限隔离（只展示，不限制）
- ❌ 异步抽帧（先同步，慢了再优化）
- ❌ 前端界面（单独 brainstorm）
