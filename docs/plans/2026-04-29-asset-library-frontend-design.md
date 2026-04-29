# 素材库（Asset Library）前端设计文档

- **日期**: 2026-04-29
- **作者**: dify-zd 团队
- **状态**: 已确认（brainstorm 完成，待实施）
- **范围**: 前端实现（Phase 5 of asset-library project）
- **依赖**: 后端 [`2026-04-28-asset-library-design.md`](./2026-04-28-asset-library-design.md) — 已完成（HEAD `37ab43022`）

---

## 1. 背景与定位

素材库前端是 creator 域的资产管理页面，配套后端的 6 个 console API 端点。**入口位置**：sidebar "分发运营"分组下，紧挨"发布作品"。**路由**：`/creator-asset-library`。

**关键定位：**

- 用户主动整理素材的**独立管理页面**，不做嵌入式选择器（YAGNI，下游 social-publish/creator-task 真有需求再补）
- **Tab 分类型 + 双形态列表**：图片/视频用网格（缩略图为核心），音频/提示词用表格（紧凑信息密度）
- **拖拽即上传 + 批量并发**：元数据用文件名做默认，后续在 drawer 里编辑
- **右侧 drawer 看详情/编辑**：列表保持可见，连续操作不打断上下文

---

## 2. 架构定位

```
web/
├── app/(creatorLayout)/creator-asset-library/
│   ├── page.tsx                              # 极薄入口
│   └── _components/                          # 私有组件，不被外部导入
│       ├── asset-library-page.tsx            # 顶层组装
│       ├── asset-tabs.tsx
│       ├── asset-filter-bar.tsx
│       ├── asset-grid.tsx + asset-card.tsx
│       ├── asset-list.tsx + asset-row.tsx
│       ├── upload-dropzone.tsx
│       ├── prompt-dialog.tsx
│       ├── asset-detail-drawer.tsx
│       ├── delete-confirm-dialog.tsx
│       └── pagination.tsx
├── contract/console/asset-library.ts         # 5 个 JSON 端点 + 共享类型
├── service/
│   ├── asset-library.ts                      # uploadAssetFile (multipart)
│   └── use-asset-library.ts                  # 6 个 TanStack Query hooks
├── i18n/{en-US,zh-Hans}/asset-library.json
└── app/components/creator/sidebar.tsx        # 修改：加入导航项
```

**关键设计决策：**

- **状态管理（参考 `creator-works` 惯例）**：列表筛选/tab/分页用 `useState`；drawer 状态用 URL `?asset_id=xxx`（可分享详情链接、刷新保留、浏览器后退自然关闭）
- **上传进度 state 提升到页面级**：跨 tab 切换不丢失正在上传的文件
- **JSON 端点走 oRPC**（与 `explore` / `billing` / `try-app` 同款），文件上传走 `service/base.ts` 的 `upload()` helper（XMLHttpRequest，支持进度）

---

## 3. oRPC Contracts

**`web/contract/console/asset-library.ts`**

写法严格匹配 Dify 现有模式（`base.route` + `type<>()` + 三段 input 结构 `{ params, query, body }`）。**不用 Zod**（项目里 contract 用纯 TS 类型断言）。

```ts
import { type } from '@orpc/contract'
import { base } from '../base'

export type AssetType = 'image' | 'audio' | 'video' | 'prompt'

export type PromptVariable = {
  name: string
  type: 'string' | 'number' | 'boolean'
  default?: string | number | boolean | null
  description?: string | null
}

export type AssetCreator = {
  id: string
  name: string
  avatar: string | null
}

export type AssetLibraryItem = {
  id: string
  tenant_id: string
  asset_type: AssetType
  name: string
  description: string | null
  tags: string[]
  category: string | null
  upload_file_id: string | null
  cover_url: string | null
  signed_url: string | null
  duration: number | null
  width: number | null
  height: number | null
  file_size: number | null
  content: string | null
  prompt_variables: PromptVariable[]
  created_by: AssetCreator | null
  created_at: number
  updated_at: number
}

export type AssetLibraryListResponse = {
  data: AssetLibraryItem[]
  total: number
  page: number
  limit: number
  has_more: boolean
}

export const assetLibraryListContract = base
  .route({ method: 'GET', path: '/asset-library' })
  .input(type<{
    query?: {
      type?: AssetType
      keyword?: string
      category?: string
      tags?: string[]
      page?: number
      limit?: number
    }
  }>())
  .output(type<AssetLibraryListResponse>())

export const assetLibraryDetailContract = base
  .route({ method: 'GET', path: '/asset-library/{asset_id}' })
  .input(type<{ params: { asset_id: string } }>())
  .output(type<AssetLibraryItem>())

export const assetLibraryPatchContract = base
  .route({ method: 'PATCH', path: '/asset-library/{asset_id}' })
  .input(type<{
    params: { asset_id: string }
    body: {
      name?: string
      description?: string | null
      tags?: string[]
      category?: string | null
      content?: string
      prompt_variables?: PromptVariable[]
    }
  }>())
  .output(type<AssetLibraryItem>())

export const assetLibraryDeleteContract = base
  .route({ method: 'DELETE', path: '/asset-library/{asset_id}' })
  .input(type<{ params: { asset_id: string } }>())
  .output(type<unknown>())

export const assetLibraryCreatePromptContract = base
  .route({ method: 'POST', path: '/asset-library/prompts' })
  .input(type<{
    body: {
      name: string
      content: string
      prompt_variables?: PromptVariable[]
      description?: string | null
      tags?: string[]
      category?: string | null
    }
  }>())
  .output(type<AssetLibraryItem>())
```

**`web/contract/router.ts`**：紧挨 explore 那一组 import 加进去 + namespace 注册。

---

## 4. Service 层

### 4.1 文件上传（multipart，走 base.ts 的 upload helper）

**`web/service/asset-library.ts`**：

```ts
import { upload } from './base'
import type { AssetLibraryItem } from '@/contract/console/asset-library'

export type UploadAssetFileBody = {
  file: File
  asset_type: 'image' | 'audio' | 'video'
  name?: string
  tags?: string[]
  category?: string
  description?: string
  onProgress?: (percent: number) => void
}

export const uploadAssetFile = async (body: UploadAssetFileBody): Promise<AssetLibraryItem> => {
  const fd = new FormData()
  fd.append('file', body.file)
  fd.append('asset_type', body.asset_type)
  if (body.name) fd.append('name', body.name)
  if (body.description) fd.append('description', body.description)
  fd.append('tags', JSON.stringify(body.tags ?? []))
  if (body.category) fd.append('category', body.category)

  const xhr = new XMLHttpRequest()
  if (body.onProgress) {
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        body.onProgress!(Math.round((e.loaded / e.total) * 100))
    }
  }
  const res = await upload(
    { xhr, data: fd, method: 'POST' },
    false,
    '/asset-library/files',
  )
  return res as unknown as AssetLibraryItem
}
```

### 4.2 TanStack Query hooks（手动 queryFn 风格，与 use-billing 一致）

**`web/service/use-asset-library.ts`**：

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consoleClient, consoleQuery } from '@/service/client'
import { uploadAssetFile, type UploadAssetFileBody } from './asset-library'

export const useAssetLibraryList = (query: {
  type?: AssetType, keyword?: string, category?: string,
  tags?: string[], page?: number, limit?: number,
}) => useQuery({
  queryKey: consoleQuery.assetLibrary.list.queryKey({ input: { query } }),
  queryFn: () => consoleClient.assetLibrary.list({ query }),
})

export const useAssetDetail = (assetId: string | null) => useQuery({
  queryKey: consoleQuery.assetLibrary.detail.queryKey({
    input: { params: { asset_id: assetId ?? '' } },
  }),
  queryFn: () => consoleClient.assetLibrary.detail({
    params: { asset_id: assetId! },
  }),
  enabled: !!assetId,
})

export const usePatchAsset = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: {
      asset_id: string,
      body: Parameters<typeof consoleClient.assetLibrary.patch>[0]['body']
    }) => consoleClient.assetLibrary.patch({
      params: { asset_id: input.asset_id },
      body: input.body,
    }),
    onSuccess: () => qc.invalidateQueries({
      queryKey: consoleQuery.assetLibrary.list.key(),
    }),
  })
}

export const useDeleteAsset = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (assetId: string) => consoleClient.assetLibrary.delete({
      params: { asset_id: assetId },
    }),
    onSuccess: () => qc.invalidateQueries({
      queryKey: consoleQuery.assetLibrary.list.key(),
    }),
  })
}

export const useCreatePromptAsset = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Parameters<typeof consoleClient.assetLibrary.createPrompt>[0]['body']) =>
      consoleClient.assetLibrary.createPrompt({ body }),
    onSuccess: () => qc.invalidateQueries({
      queryKey: consoleQuery.assetLibrary.list.key(),
    }),
  })
}

export const useUploadAssetFile = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: UploadAssetFileBody) => uploadAssetFile(body),
    onSuccess: () => qc.invalidateQueries({
      queryKey: consoleQuery.assetLibrary.list.key(),
    }),
  })
}
```

---

## 5. 路由 + 页面骨架

### 5.1 极薄入口

```tsx
// web/app/(creatorLayout)/creator-asset-library/page.tsx
import AssetLibraryPage from './_components/asset-library-page'
export default function Page() { return <AssetLibraryPage /> }
```

### 5.2 状态分布

| 状态 | 存储 | 理由 |
|---|---|---|
| `tab / keyword / category / tags / page` | `useState` | 跟 creator-works 一致；筛选短期、不需分享 |
| `asset_id` (drawer) | URL `?asset_id` | 可分享详情链接、刷新保持、浏览器后退自然关闭 |
| 上传进度 (per-file) | `AssetLibraryPage` 层 useState | 跨 tab 切换不丢失 |

### 5.3 顶层组装

```tsx
// _components/asset-library-page.tsx
'use client'

import { useState } from 'react'
import { useSearchParams, useRouter, usePathname } from 'next/navigation'
import { useTranslation } from 'react-i18next'
import type { AssetType } from '@/contract/console/asset-library'
// 子组件 + hooks 导入

type TabValue = 'all' | AssetType

export default function AssetLibraryPage() {
  const { t } = useTranslation('assetLibrary')
  const sp = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  const [tab, setTab] = useState<TabValue>('all')
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState<string | undefined>()
  const [tags, setTags] = useState<string[]>([])
  const [page, setPage] = useState(1)

  const detailAssetId = sp.get('asset_id') ?? null
  const setDetailAssetId = (id: string | null) => {
    const next = new URLSearchParams(sp.toString())
    if (id) next.set('asset_id', id)
    else next.delete('asset_id')
    router.replace(`${pathname}?${next.toString()}`)
  }

  const list = useAssetLibraryList({
    type: tab === 'all' ? undefined : tab,
    keyword: keyword || undefined,
    category, tags: tags.length ? tags : undefined,
    page, limit: 20,
  })

  const isGridMode = tab === 'image' || tab === 'video' || tab === 'all'
  const handleTabChange = (v: TabValue) => { setTab(v); setPage(1) }

  return (
    <div className="flex h-full flex-col px-8 py-6">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('title')}</h1>
        {tab === 'prompt' && <PromptDialog onCreated={() => list.refetch()} />}
      </header>

      <AssetTabs value={tab} onChange={handleTabChange} />
      <AssetFilterBar
        keyword={keyword} category={category} tags={tags}
        onKeywordChange={v => { setKeyword(v); setPage(1) }}
        onCategoryChange={v => { setCategory(v); setPage(1) }}
        onTagsChange={v => { setTags(v); setPage(1) }}
      />

      {tab !== 'prompt' && (
        <UploadDropzone
          defaultAssetType={tab === 'all' ? 'image' : tab}
          onUploaded={() => list.refetch()}
        />
      )}

      {isGridMode
        ? <AssetGrid items={list.data?.data ?? []}
                     loading={list.isLoading}
                     onSelect={setDetailAssetId} />
        : <AssetList items={list.data?.data ?? []}
                     loading={list.isLoading}
                     onSelect={setDetailAssetId} />}

      <Pagination
        page={page} total={list.data?.total ?? 0} limit={20}
        hasMore={list.data?.has_more ?? false}
        onChange={setPage}
      />

      <AssetDetailDrawer
        assetId={detailAssetId}
        onClose={() => setDetailAssetId(null)}
        onMutated={() => list.refetch()}
      />
    </div>
  )
}
```

---

## 6. 核心组件清单

### `AssetTabs`
- Props: `value: TabValue, onChange: (v: TabValue) => void`
- 5 个 tab：`全部 / 图片 / 视频 / 音频 / 提示词`
- 复用现有 `web/app/components/base/` 下的 Tabs 组件

### `AssetFilterBar`
- Props: `keyword, category, tags` + 三个 `onChange` 回调
- 三列：搜索 input（debounce 300ms）+ category select + tags 多选输入（Enter 添加 chip）

### `AssetGrid`（图/视频）
- CSS Grid，最小宽 180px，比例 4:3
- 图片 item：`signed_url` 作 `<img>` src；hover 显示标题 + tags 浮层
- 视频 item：`cover_url` 作背景图；右下角时长角标 `15.2s`；点击时显示播放图标
- 加载中：6 个 skeleton；空态：插画 + 提示拖拽上传

### `AssetList`（音频/提示词）
- 表格：名称 / 类型 / 时长（音频）/ 标签 / 创建人 / 创建时间 / 操作
- 提示词 row：名称 + 内容前 50 字预览（灰色）

### `UploadDropzone`
- 拖入根据 MIME 自动判断 `asset_type`（不在白名单的拒绝并 toast）
- 多文件并发：每个文件一个进度 chip
- 进度 state 由父组件 `AssetLibraryPage` 持有（跨 tab 不丢失）
- 失败：chip 变红 + 错误信息 + 关闭 X

### `PromptDialog`
- Dialog 内部：name / content (textarea, 8 行) / 描述 / 标签 chips / 分类 input / 变量定义动态表
- 变量表每行：name + type select + default input + description + 删除 + 底部"+ 添加变量"
- 提交：`useCreatePromptAsset` → 成功 toast + 关闭 + onCreated()
- 422 prompt_variables 错误：定位到具体行展示

### `AssetDetailDrawer`
- 左侧 60% 预览，右侧 40% 编辑表单
- 4 种预览：image (`<img>` from `signed_url`) / video (`<video>` controls) / audio (`<audio>` controls) / prompt (代码块 + 复制按钮)
- 表单：name / description / tags / category / content（仅 prompt）/ prompt_variables（仅 prompt）
- 底部：保存（dirty 时高亮）+ 删除（红色，触发 confirm）
- 保存：`usePatchAsset` → 成功不关 drawer + onMutated() 刷新列表

### `DeleteConfirmDialog`
- "确定删除「{name}」？此操作不可撤销。"
- 复用现有 confirm dialog（`web/app/components/base/ui/`）

### `Pagination`
- 上一页 / 当前/总页数 / 下一页
- `total < limit` 时不渲染

---

## 7. i18n + Sidebar

### 7.1 i18n key 集合（约 40 个）

`web/i18n/{en-US,zh-Hans}/asset-library.json` 同 key 集：

```json
{
  "title": "Asset Library",
  "tabs": { "all": "All", "image": "Images", "video": "Videos", "audio": "Audio", "prompt": "Prompts" },
  "filters": {
    "searchPlaceholder": "Search by name or description",
    "categoryAll": "All categories",
    "tagsPlaceholder": "Type a tag and press Enter"
  },
  "upload": {
    "dropzoneIdle": "Drag files here or click to select",
    "dropzoneActive": "Release to upload",
    "uploading": "Uploading {{filename}}",
    "uploadFailed": "Upload failed: {{reason}}",
    "unsupportedMime": "Unsupported file type"
  },
  "prompt": {
    "newButton": "New Prompt",
    "dialogTitle": "Create Prompt Asset",
    "fields": { "name": "Name", "content": "Content", "description": "Description",
                "tags": "Tags", "category": "Category",
                "variables": "Variables", "addVariable": "Add Variable" },
    "variableFields": { "name": "Variable name", "type": "Type",
                         "default": "Default", "description": "Description (optional)" }
  },
  "detail": {
    "save": "Save", "delete": "Delete",
    "savedToast": "Saved", "deletedToast": "Deleted",
    "deleteConfirmTitle": "Delete asset",
    "deleteConfirmBody": "Are you sure you want to delete '{{name}}'? This cannot be undone."
  },
  "empty": {
    "all": "Nothing here yet — drag files in or create a prompt",
    "byType": "No {{type}} assets yet"
  },
  "errors": {
    "loadFailed": "Failed to load assets",
    "validationFailed": "Validation failed: {{reason}}"
  },
  "sidebar": "Asset Library"
}
```

zh-Hans 对应翻译（"Asset Library" → "素材库"，etc）。

### 7.2 Namespace 注册

修改 `web/i18n/{en-US,zh-Hans}/index.ts` 注册 `asset-library` namespace。

### 7.3 Sidebar 接入

修改 `web/app/components/creator/sidebar.tsx`：

```tsx
const isAssetLibrary = pathname === '/creator-asset-library'

// 在"分发运营"组里"发布作品"下面：
<NavItem
  href="/creator-asset-library"
  icon={RiFolderImageLine}  /* 实施时挑合适图标 */
  label={t('sidebar')}      /* 用 i18n */
  active={isAssetLibrary}
  collapsed={collapsed}
/>
```

> **范围控制**：只把素材库这项做 i18n；其他 sidebar 项（首页、发布作品）保持中文硬编码，避免改到不相关代码。

---

## 8. 测试策略

遵循 `web/CLAUDE.md` 强制约束：`frontend-testing` skill + `docs/test.md` 是 mandatory。

### 8.1 单测覆盖矩阵

| 单元 | 关键测试点 |
|---|---|
| `AssetTabs` | 切换触发 onChange、value 反映 active 样式 |
| `AssetFilterBar` | keyword debounce 300ms、tags Enter 添加/X 删除、空值不发请求 |
| `AssetGrid` | items=[] 显示空态、loading 显示 skeleton、点击触发 onSelect |
| `AssetList` | 同上 + prompt 内容预览截断到 50 字 |
| `UploadDropzone` | 多文件并发、MIME 拒绝、进度回调、失败 toast |
| `PromptDialog` | 必填校验、variable 行增删、提交调 hook、422 错误展示 |
| `AssetDetailDrawer` | assetId=null 不渲染、4 种 type 预览、dirty 状态、保存/删除流程 |
| `DeleteConfirmDialog` | confirm 触发 onConfirm、cancel 关闭 |
| `useAssetLibraryList` | query 参数透传、tab=all 不带 type、tags=[] 不带 tags |
| `usePatchAsset` | 成功 invalidate list、错误传 toast |
| `uploadAssetFile` (service) | FormData 字段正确、xhr.upload.onprogress 调用、失败抛错 |

### 8.2 Mocking

MSW mock console API responses，参考项目现有 mock 设置。

### 8.3 i18n 测试

测试时切到 en-US 断言英文 key 可见，确保所有可见字符串都走 i18n（无中文硬编码逃逸）。

### 8.4 E2E

**先不做**（YAGNI）。等核心组件单测覆盖好且后端 task 16 手测通过再补。

---

## 9. 实施分阶段

### Phase 1：契约 + Service（半天）
1. `contract/console/asset-library.ts` + 5 个 contract + 共享类型
2. `contract/router.ts` 注册 console namespace
3. `service/asset-library.ts` — `uploadAssetFile()`
4. `service/use-asset-library.ts` — 6 个 hooks
5. Service 层单测：`uploadAssetFile` (FormData / 进度 / 失败)；hooks 用 MSW

### Phase 2：i18n + sidebar（半天）
6. `i18n/{en-US,zh-Hans}/asset-library.json`
7. namespace 注册
8. sidebar 加 NavItem
9. `creator-asset-library/page.tsx` 极薄入口

### Phase 3：基础组件（1 天）
10. `AssetTabs / AssetFilterBar / Pagination`
11. `AssetGrid / AssetCard`
12. `AssetList / AssetRow`
13. 每组件 TDD 红→绿

### Phase 4：上传 + 提示词（1 天）
14. `UploadDropzone`（拖拽 + 并发 + 进度 chip）
15. `PromptDialog`（含 variable 动态表）

### Phase 5：详情 drawer（1 天）
16. `AssetDetailDrawer`（4 种预览 + 编辑 + dirty）
17. `DeleteConfirmDialog`

### Phase 6：组装 + 联调（半天）
18. `AssetLibraryPage` 顶层组装
19. drawer URL state 同步
20. 全套测试 + 80% 覆盖
21. `pnpm lint:fix` + `pnpm type-check:tsgo`
22. dev 起来手测一遍完整流程

**总工时估计：4-5 天**

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| `consoleClient` 自动从 router 生成时漏注册 | runtime 报错 | router.ts 注册后立即跑 type-check |
| `signed_url` 后端返回 null | 图片视频显示破图 | UI 加 fallback 图标；后端 task 16 手测确认 URL 实际可达 |
| 拖拽上传巨大视频（500MB+）阻塞浏览器 | UX 卡顿 | UploadDropzone 单文件限 200MB（前端预检），超大 toast 拒绝 |
| oRPC contract 注册路径与后端 url_prefix 不匹配 | 404 | `base.route.path` 用 `/asset-library`（不带 `/console/api` 前缀，client 自动加） |
| 拖拽上传时切 tab 丢失进度 chip | 进度不可见 | 进度 state 提升到 `AssetLibraryPage` 层级，跨 tab 保留 |

---

## 11. 不做（YAGNI）

- ❌ 选择器弹窗（嵌入 social-publish / creator-task）
- ❌ 回收站 / 软删除
- ❌ 标签自动补全（候选 tag 端点）
- ❌ 批量选择 + 批量删除
- ❌ 上传断点续传 / 大文件分片
- ❌ 视频实时压缩 / 二次封面选择
- ❌ E2E Playwright（先靠单测覆盖）

---

## 12. 已确认的范围（Brainstorm 决议）

| | |
|---|---|
| 入口 | `/creator-asset-library`，sidebar "分发运营"组 |
| 列表形态 | Tab + 双形态（图/视频网格、音频/提示词列表） |
| 上传 | 拖拽即上传 + 批量；prompt 单独 dialog |
| 详情/编辑 | 右侧 drawer + confirm 删除 |
| 筛选 | 搜索 + category 下拉 + tags 手动输入 |
| 数据获取 | JSON oRPC，文件 `service/base.ts upload()` |
| i18n | 中英双语完整 |
| 状态管理 | useState 主，URL 仅管 drawer |
