# 素材库（Asset Library）前端实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Dify 素材库前端 —— `/creator-asset-library` 页面 + sidebar 导航接入 + 5 个 oRPC contracts + 文件上传 service + 6 个 React 组件 + 中英 i18n。

**Architecture:** Tab 分类型 + 双形态列表（图/视频网格、音频/提示词表格）+ 拖拽即上传（多文件并发）+ 右侧 drawer 编辑 + URL `?asset_id` 驱动 drawer。JSON 端点走 `base.route` + `type<>()` oRPC contract（与 explore/billing 同款），文件上传走 `service/base.ts` 的 `upload()` helper（XMLHttpRequest 支持进度）。

**Tech Stack:** Next.js + TypeScript + React + TanStack Query + oRPC + Tailwind；测试 Vitest + RTL + MSW；i18n react-i18next；包管理 pnpm。

**Reference design:** [`docs/plans/2026-04-29-asset-library-frontend-design.md`](./2026-04-29-asset-library-frontend-design.md)

**Backend reference:** Already done at `37ab43022..` on dify-zd. 5 JSON endpoints + 1 multipart endpoint live at `/console/api/asset-library/...`. Response shape is in design doc §3.

**Code standards:** 严格遵守 `web/CLAUDE.md`：
- 通过 `pnpm lint:fix` 和 `pnpm type-check:tsgo` 检查
- 所有用户可见字符串必须走 `useTranslation('assetLibrary')`，**禁止硬编码**
- `frontend-query-mutation` skill 是 mandatory
- 测试遵循 `web/docs/test.md` + `frontend-testing` skill
- Overlay 组件只用 `@/app/components/base/ui/*`（per `web/docs/overlay-migration.md`）

---

## Phase 1：契约 + Service 层

### Task 1：oRPC Contracts

**Files:**
- Create: `web/contract/console/asset-library.ts`

**Step 1: Write the file**

```ts
// web/contract/console/asset-library.ts
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

**Step 2: Type-check**

Run: `cd web && pnpm type-check:tsgo`
Expected: No errors related to `asset-library.ts`.

**Step 3: Commit**

```bash
git add web/contract/console/asset-library.ts
git commit -m "feat(asset-library/web): add oRPC contracts"
```

---

### Task 2：Register contracts in router

**Files:**
- Modify: `web/contract/router.ts`

**Step 1: Add import block alphabetically (after the `try-app` import on line 36)**

```ts
import {
  assetLibraryCreatePromptContract,
  assetLibraryDeleteContract,
  assetLibraryDetailContract,
  assetLibraryListContract,
  assetLibraryPatchContract,
} from './console/asset-library'
```

**Step 2: Add namespace to `consoleRouterContract` (after `apps`, alphabetical order)**

```ts
  assetLibrary: {
    list: assetLibraryListContract,
    detail: assetLibraryDetailContract,
    patch: assetLibraryPatchContract,
    delete: assetLibraryDeleteContract,
    createPrompt: assetLibraryCreatePromptContract,
  },
```

**Step 3: Type-check**

Run: `cd web && pnpm type-check:tsgo`
Expected: No errors.

**Step 4: Verify consoleClient resolves**

Run:
```bash
cd web
pnpm tsx -e "import { consoleQuery } from './service/client.ts'; console.log(typeof consoleQuery.assetLibrary.list)"
```
Expected: prints `object`.

If `tsx` is not available, skip — Task 4's hook tests will exercise this path.

**Step 5: Commit**

```bash
git add web/contract/router.ts
git commit -m "feat(asset-library/web): register asset library contracts"
```

---

### Task 3：File upload service

**Files:**
- Create: `web/service/asset-library.ts`
- Test: `web/service/asset-library.spec.ts`

**Step 1: Write the failing test**

```ts
// web/service/asset-library.spec.ts
import { describe, expect, it, vi } from 'vitest'

vi.mock('./base', () => ({
  upload: vi.fn(),
}))

import { upload } from './base'
import { uploadAssetFile } from './asset-library'

describe('uploadAssetFile', () => {
  it('builds FormData with file + asset_type + JSON-encoded tags', async () => {
    const mockUpload = vi.mocked(upload)
    mockUpload.mockResolvedValue({ id: 'asset-1' } as never)

    const file = new File([new Uint8Array([1, 2, 3])], 'pic.png', { type: 'image/png' })
    await uploadAssetFile({
      file,
      asset_type: 'image',
      name: '我的图',
      tags: ['a', 'b'],
      category: '测试',
    })

    expect(mockUpload).toHaveBeenCalledTimes(1)
    const [opts, isPublic, url] = mockUpload.mock.calls[0]
    expect(isPublic).toBe(false)
    expect(url).toBe('/asset-library/files')
    expect(opts.data).toBeInstanceOf(FormData)
    const fd = opts.data as FormData
    expect(fd.get('asset_type')).toBe('image')
    expect(fd.get('name')).toBe('我的图')
    expect(fd.get('tags')).toBe('["a","b"]')
    expect(fd.get('category')).toBe('测试')
    expect(fd.get('file')).toBeInstanceOf(File)
  })

  it('omits optional fields when not provided; sends empty tags array', async () => {
    const mockUpload = vi.mocked(upload)
    mockUpload.mockResolvedValue({ id: 'asset-2' } as never)

    const file = new File(['x'], 'x.mp3', { type: 'audio/mpeg' })
    await uploadAssetFile({ file, asset_type: 'audio' })

    const fd = vi.mocked(upload).mock.calls.at(-1)![0].data as FormData
    expect(fd.get('name')).toBeNull()
    expect(fd.get('description')).toBeNull()
    expect(fd.get('category')).toBeNull()
    expect(fd.get('tags')).toBe('[]')
  })

  it('wires onProgress to xhr.upload.onprogress', async () => {
    const mockUpload = vi.mocked(upload)
    mockUpload.mockImplementation(async (opts) => {
      // Simulate xhr firing a progress event
      opts.xhr.upload.onprogress?.({
        lengthComputable: true,
        loaded: 50,
        total: 100,
      } as ProgressEvent)
      return { id: 'asset-3' } as never
    })

    const events: number[] = []
    await uploadAssetFile({
      file: new File(['x'], 'x.png', { type: 'image/png' }),
      asset_type: 'image',
      onProgress: p => events.push(p),
    })
    expect(events).toEqual([50])
  })
})
```

**Step 2: Run — verify FAIL**

Run: `cd web && pnpm vitest run service/asset-library.spec.ts`
Expected: FAIL — `uploadAssetFile` does not exist.

**Step 3: Implement**

```ts
// web/service/asset-library.ts
import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { upload } from './base'

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

**Step 4: Run — verify PASS**

Run: `cd web && pnpm vitest run service/asset-library.spec.ts`
Expected: 3 passed.

**Step 5: Lint + format**

Run: `cd web && pnpm lint:fix web/service/asset-library.ts web/service/asset-library.spec.ts`

**Step 6: Commit**

```bash
git add web/service/asset-library.ts web/service/asset-library.spec.ts
git commit -m "feat(asset-library/web): file upload service"
```

---

### Task 4：TanStack Query hooks

**Files:**
- Create: `web/service/use-asset-library.ts`
- Test: `web/service/use-asset-library.spec.ts`

**Step 1: Write failing tests**

Mirror the style of `web/service/use-billing.ts` (check that file). Write tests using a `QueryClient` test wrapper. Cover:
- `useAssetLibraryList(query)` calls `consoleClient.assetLibrary.list({ query })` and returns `data`
- `useAssetDetail(null)` does NOT fire (enabled: false)
- `useAssetDetail("id-1")` calls with `{ params: { asset_id: "id-1" } }`
- `usePatchAsset()` mutates with `{ params, body }` and on success invalidates the list queryKey
- `useDeleteAsset()` similar (mutates with id, invalidates list)
- `useCreatePromptAsset()` mutates with `{ body }` and invalidates list
- `useUploadAssetFile()` calls `uploadAssetFile()` and invalidates list

Look at `web/service/use-apps.spec.ts` (or any existing `use-*.spec.ts`) for the test wrapper pattern.

```ts
// web/service/use-asset-library.spec.ts
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

vi.mock('./client', () => ({
  consoleClient: {
    assetLibrary: {
      list: vi.fn(),
      detail: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      createPrompt: vi.fn(),
    },
  },
  consoleQuery: {
    assetLibrary: {
      list: { queryKey: vi.fn(({ input }) => ['assetLibrary.list', input]),
              key: vi.fn(() => ['assetLibrary.list']) },
      detail: { queryKey: vi.fn(({ input }) => ['assetLibrary.detail', input]) },
    },
  },
}))

vi.mock('./asset-library', () => ({
  uploadAssetFile: vi.fn(),
}))

import { consoleClient } from './client'
import { uploadAssetFile } from './asset-library'
import {
  useAssetDetail,
  useAssetLibraryList,
  useCreatePromptAsset,
  useDeleteAsset,
  usePatchAsset,
  useUploadAssetFile,
} from './use-asset-library'

const wrapper = ({ children }: { children: ReactNode }) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('useAssetLibraryList', () => {
  it('calls list with the given query', async () => {
    vi.mocked(consoleClient.assetLibrary.list).mockResolvedValue({
      data: [], total: 0, page: 1, limit: 20, has_more: false,
    })
    const { result } = renderHook(
      () => useAssetLibraryList({ type: 'image', page: 1, limit: 20 }),
      { wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(consoleClient.assetLibrary.list).toHaveBeenCalledWith({
      query: { type: 'image', page: 1, limit: 20 },
    })
  })
})

describe('useAssetDetail', () => {
  it('is disabled when assetId is null', () => {
    const { result } = renderHook(() => useAssetDetail(null), { wrapper })
    expect(result.current.fetchStatus).toBe('idle')
    expect(consoleClient.assetLibrary.detail).not.toHaveBeenCalled()
  })

  it('fetches when assetId is provided', async () => {
    vi.mocked(consoleClient.assetLibrary.detail).mockResolvedValue({} as never)
    const { result } = renderHook(() => useAssetDetail('id-1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(consoleClient.assetLibrary.detail).toHaveBeenCalledWith({
      params: { asset_id: 'id-1' },
    })
  })
})

// Add similar tests for usePatchAsset, useDeleteAsset, useCreatePromptAsset, useUploadAssetFile
// Each verifies: (a) the underlying call signature, (b) that on success the list queryKey is invalidated
```

> **Note:** check the actual shape of `consoleQuery.X.queryKey` and `consoleQuery.X.key()` used in `web/service/use-billing.ts` — replicate the same access pattern. If the project uses `consoleQuery.assetLibrary.list.key()` to get the list-level key, mock that.

**Step 2: Run — verify FAIL**

Run: `cd web && pnpm vitest run service/use-asset-library.spec.ts`
Expected: FAIL — module does not exist.

**Step 3: Implement**

```ts
// web/service/use-asset-library.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AssetType, PromptVariable } from '@/contract/console/asset-library'
import { consoleClient, consoleQuery } from '@/service/client'
import { uploadAssetFile, type UploadAssetFileBody } from './asset-library'

type ListQuery = {
  type?: AssetType
  keyword?: string
  category?: string
  tags?: string[]
  page?: number
  limit?: number
}

export const useAssetLibraryList = (query: ListQuery) => useQuery({
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

type PatchInput = {
  asset_id: string
  body: {
    name?: string
    description?: string | null
    tags?: string[]
    category?: string | null
    content?: string
    prompt_variables?: PromptVariable[]
  }
}

export const usePatchAsset = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: PatchInput) => consoleClient.assetLibrary.patch({
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

type CreatePromptBody = {
  name: string
  content: string
  prompt_variables?: PromptVariable[]
  description?: string | null
  tags?: string[]
  category?: string | null
}

export const useCreatePromptAsset = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CreatePromptBody) =>
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

**Step 4: Run — verify PASS**

Run: `cd web && pnpm vitest run service/use-asset-library.spec.ts`
Expected: All tests pass.

**Step 5: Lint + type-check**

```bash
cd web
pnpm lint:fix service/use-asset-library.ts service/use-asset-library.spec.ts
pnpm type-check:tsgo
```

**Step 6: Commit**

```bash
git add web/service/use-asset-library.ts web/service/use-asset-library.spec.ts
git commit -m "feat(asset-library/web): TanStack Query hooks"
```

---

## Phase 2：i18n + Sidebar + 路由入口

### Task 5：i18n JSON files

**Files:**
- Create: `web/i18n/en-US/asset-library.json`
- Create: `web/i18n/zh-Hans/asset-library.json`

**Step 1: Write `web/i18n/en-US/asset-library.json`**

```json
{
  "title": "Asset Library",
  "tabs": {
    "all": "All",
    "image": "Images",
    "video": "Videos",
    "audio": "Audio",
    "prompt": "Prompts"
  },
  "filters": {
    "searchPlaceholder": "Search by name or description",
    "categoryAll": "All categories",
    "categoryPlaceholder": "Filter by category",
    "tagsPlaceholder": "Type a tag and press Enter"
  },
  "upload": {
    "dropzoneIdle": "Drag files here or click to select",
    "dropzoneActive": "Release to upload",
    "uploading": "Uploading {{filename}}",
    "uploadFailed": "Upload failed: {{reason}}",
    "unsupportedMime": "Unsupported file type: {{mime}}",
    "fileTooLarge": "File too large (max 200MB)"
  },
  "prompt": {
    "newButton": "New Prompt",
    "dialogTitle": "Create Prompt Asset",
    "fields": {
      "name": "Name",
      "content": "Content",
      "description": "Description",
      "tags": "Tags",
      "category": "Category",
      "variables": "Variables",
      "addVariable": "Add Variable"
    },
    "variableFields": {
      "name": "Variable name",
      "type": "Type",
      "default": "Default",
      "description": "Description (optional)"
    },
    "validation": {
      "nameRequired": "Name is required",
      "contentRequired": "Content is required",
      "variableNameInvalid": "Variable name must match [A-Za-z_][A-Za-z0-9_]*"
    },
    "create": "Create",
    "cancel": "Cancel"
  },
  "detail": {
    "save": "Save",
    "delete": "Delete",
    "savedToast": "Saved",
    "deletedToast": "Deleted",
    "deleteConfirmTitle": "Delete asset",
    "deleteConfirmBody": "Are you sure you want to delete '{{name}}'? This cannot be undone.",
    "deleteConfirm": "Delete",
    "deleteCancel": "Cancel",
    "copyContent": "Copy",
    "copiedToast": "Copied to clipboard"
  },
  "empty": {
    "all": "Nothing here yet — drag files in or create a prompt",
    "byType": "No {{type}} assets yet"
  },
  "errors": {
    "loadFailed": "Failed to load assets",
    "validationFailed": "Validation failed: {{reason}}"
  },
  "pagination": {
    "previous": "Previous",
    "next": "Next",
    "page": "Page {{current}} of {{total}}"
  },
  "sidebar": "Asset Library"
}
```

**Step 2: Write `web/i18n/zh-Hans/asset-library.json` (same keys, Chinese values)**

```json
{
  "title": "素材库",
  "tabs": {
    "all": "全部",
    "image": "图片",
    "video": "视频",
    "audio": "音频",
    "prompt": "提示词"
  },
  "filters": {
    "searchPlaceholder": "按名称或描述搜索",
    "categoryAll": "全部分类",
    "categoryPlaceholder": "按分类筛选",
    "tagsPlaceholder": "输入标签后按回车添加"
  },
  "upload": {
    "dropzoneIdle": "拖拽文件到此处，或点击选择",
    "dropzoneActive": "松开以上传",
    "uploading": "正在上传 {{filename}}",
    "uploadFailed": "上传失败：{{reason}}",
    "unsupportedMime": "不支持的文件类型：{{mime}}",
    "fileTooLarge": "文件过大（最大 200MB）"
  },
  "prompt": {
    "newButton": "新建提示词",
    "dialogTitle": "新建提示词素材",
    "fields": {
      "name": "名称",
      "content": "内容",
      "description": "描述",
      "tags": "标签",
      "category": "分类",
      "variables": "变量",
      "addVariable": "添加变量"
    },
    "variableFields": {
      "name": "变量名",
      "type": "类型",
      "default": "默认值",
      "description": "描述（可选）"
    },
    "validation": {
      "nameRequired": "名称必填",
      "contentRequired": "内容必填",
      "variableNameInvalid": "变量名必须符合 [A-Za-z_][A-Za-z0-9_]*"
    },
    "create": "创建",
    "cancel": "取消"
  },
  "detail": {
    "save": "保存",
    "delete": "删除",
    "savedToast": "已保存",
    "deletedToast": "已删除",
    "deleteConfirmTitle": "删除素材",
    "deleteConfirmBody": "确定删除「{{name}}」？此操作不可撤销。",
    "deleteConfirm": "删除",
    "deleteCancel": "取消",
    "copyContent": "复制",
    "copiedToast": "已复制到剪贴板"
  },
  "empty": {
    "all": "还没有素材 —— 拖拽文件上传或新建提示词",
    "byType": "还没有{{type}}素材"
  },
  "errors": {
    "loadFailed": "加载素材失败",
    "validationFailed": "校验失败：{{reason}}"
  },
  "pagination": {
    "previous": "上一页",
    "next": "下一页",
    "page": "第 {{current}} 页，共 {{total}} 页"
  },
  "sidebar": "素材库"
}
```

**Step 3: Commit**

```bash
git add web/i18n/en-US/asset-library.json web/i18n/zh-Hans/asset-library.json
git commit -m "feat(asset-library/web): i18n bundles (en-US + zh-Hans)"
```

---

### Task 6：Register i18n namespace

**Files:**
- Modify: `web/i18n-config/resources.ts`

**Step 1: Open the file and add import alphabetically (after `app` line, before `billing`)**

```ts
import type assetLibrary from '../i18n/en-US/asset-library.json'
```

**Step 2: Add to `Resources` type alphabetically (after `app: typeof app,`)**

```ts
  assetLibrary: typeof assetLibrary
```

**Step 3: Type-check**

Run: `cd web && pnpm type-check:tsgo`
Expected: No errors.

**Step 4: Smoke verification**

Open `web/types/i18n.d.ts` if present and check whether namespace registration also needs updating there. If yes, add `'assetLibrary'` to whatever list it maintains. If no, skip.

> Reference: prior session note "Fixed missing socialPublish namespace in i18n resources.ts" — same pattern applies here.

**Step 5: Commit**

```bash
git add web/i18n-config/resources.ts
git commit -m "feat(asset-library/web): register i18n namespace"
```

---

### Task 7：Sidebar nav item

**Files:**
- Modify: `web/app/components/creator/sidebar.tsx`

**Step 1: Read the file** (already read partially in brainstorm) — find the "分发运营" group block (after `creator-works` NavItem around line 199-204).

**Step 2: Add NavItem after the `creator-works` one**

Add at the top of the file (with other imports):

```ts
import { RiFolderImageLine } from '@remixicon/react'
import { useTranslation } from 'react-i18next'
```

(`useTranslation` may already be imported — check first; only add if missing.)

In the component body, alongside `isCreatorWorks`:

```ts
const isAssetLibrary = pathname === '/creator-asset-library'
const { t } = useTranslation('assetLibrary')
```

In JSX, after the `<NavItem href="/creator-works" .../>`:

```tsx
<NavItem
  href="/creator-asset-library"
  icon={RiFolderImageLine}
  label={t('sidebar')}
  active={isAssetLibrary}
  collapsed={collapsed}
/>
```

> **Range control:** keep "首页" and "发布作品" hardcoded in Chinese (don't refactor them).

**Step 3: Lint + type-check**

```bash
cd web
pnpm lint:fix app/components/creator/sidebar.tsx
pnpm type-check:tsgo
```

**Step 4: Commit**

```bash
git add web/app/components/creator/sidebar.tsx
git commit -m "feat(asset-library/web): add sidebar nav item"
```

---

### Task 8：Page entry stub

**Files:**
- Create: `web/app/(creatorLayout)/creator-asset-library/page.tsx`
- Create: `web/app/(creatorLayout)/creator-asset-library/_components/asset-library-page.tsx` (placeholder)

**Step 1: Write the entry stub**

```tsx
// web/app/(creatorLayout)/creator-asset-library/page.tsx
import AssetLibraryPage from './_components/asset-library-page'

export default function Page() {
  return <AssetLibraryPage />
}
```

**Step 2: Write a placeholder component**

```tsx
// web/app/(creatorLayout)/creator-asset-library/_components/asset-library-page.tsx
'use client'

import { useTranslation } from 'react-i18next'

export default function AssetLibraryPage() {
  const { t } = useTranslation('assetLibrary')
  return (
    <div className="flex h-full flex-col px-8 py-6">
      <h1 className="text-2xl font-semibold">{t('title')}</h1>
    </div>
  )
}
```

**Step 3: Smoke run**

Start dev server (only locally — DON'T leave running):
```bash
cd web && pnpm dev
```
Visit `http://localhost:3000/creator-asset-library`. Verify:
- Sidebar shows "素材库" item active
- Page shows "素材库" title
- No console errors

Then **stop the dev server**.

**Step 4: Commit**

```bash
git add web/app/\(creatorLayout\)/creator-asset-library/
git commit -m "feat(asset-library/web): page entry + placeholder"
```

---

## Phase 3：基础组件（Tabs / FilterBar / Pagination / Grid / List）

> All components in this phase live under `_components/`. Each task: write tests first, implement, lint, commit.

### Task 9：AssetTabs

**Files:**
- Create: `_components/asset-tabs.tsx`
- Test: `_components/__tests__/asset-tabs.spec.tsx`

**Step 1: Failing test**

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AssetTabs, { type TabValue } from '../asset-tabs'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

describe('AssetTabs', () => {
  it('renders all 5 tabs', () => {
    render(<AssetTabs value="all" onChange={() => {}} />)
    ;['tabs.all', 'tabs.image', 'tabs.video', 'tabs.audio', 'tabs.prompt'].forEach((k) => {
      expect(screen.getByText(k)).toBeInTheDocument()
    })
  })

  it('marks the active tab', () => {
    render(<AssetTabs value="image" onChange={() => {}} />)
    const active = screen.getByText('tabs.image').closest('button')
    expect(active?.getAttribute('aria-current') ?? active?.dataset.active).toBeTruthy()
  })

  it('calls onChange when a tab is clicked', () => {
    const fn = vi.fn()
    render(<AssetTabs value="all" onChange={fn} />)
    fireEvent.click(screen.getByText('tabs.video'))
    expect(fn).toHaveBeenCalledWith('video' satisfies TabValue)
  })
})
```

**Step 2: Run — FAIL**

```bash
cd web && pnpm vitest run app/\(creatorLayout\)/creator-asset-library/_components/__tests__/asset-tabs.spec.tsx
```
Expected: FAIL.

**Step 3: Implement**

```tsx
// _components/asset-tabs.tsx
'use client'
import { useTranslation } from 'react-i18next'
import { cn } from '@/utils/classnames'
import type { AssetType } from '@/contract/console/asset-library'

export type TabValue = 'all' | AssetType

const TABS: TabValue[] = ['all', 'image', 'video', 'audio', 'prompt']

type Props = {
  value: TabValue
  onChange: (v: TabValue) => void
}

export default function AssetTabs({ value, onChange }: Props) {
  const { t } = useTranslation('assetLibrary')
  return (
    <div role="tablist" className="flex items-center gap-1 border-b border-divider-subtle">
      {TABS.map((tab) => {
        const active = value === tab
        return (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-current={active ? 'page' : undefined}
            data-active={active}
            onClick={() => onChange(tab)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              active
                ? 'border-primary-600 text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary',
            )}
          >
            {t(`tabs.${tab}`)}
          </button>
        )
      })}
    </div>
  )
}
```

> **Note:** verify `cn` import path — Dify usually has `@/utils/classnames` or similar. Look at any existing component for the right path.

**Step 4: Run — PASS**

Same command as Step 2; expect 3 passed.

**Step 5: Lint + commit**

```bash
cd web && pnpm lint:fix app/\(creatorLayout\)/creator-asset-library/_components/asset-tabs.tsx app/\(creatorLayout\)/creator-asset-library/_components/__tests__/asset-tabs.spec.tsx
git add web/app/\(creatorLayout\)/creator-asset-library/_components/asset-tabs.tsx \
        web/app/\(creatorLayout\)/creator-asset-library/_components/__tests__/asset-tabs.spec.tsx
git commit -m "feat(asset-library/web): AssetTabs component"
```

---

### Task 10：AssetFilterBar

**Files:**
- Create: `_components/asset-filter-bar.tsx`
- Test: `_components/__tests__/asset-filter-bar.spec.tsx`

**Step 1: Failing tests**

Cover:
1. Renders search input + category select + tags input
2. Typing in search debounces 300ms before calling `onKeywordChange`
3. Typing tag + Enter adds chip; X on chip removes it
4. Empty input on Enter does nothing
5. Already-existing tag is not added twice

Use `vi.useFakeTimers()` for the debounce test.

```tsx
import { render, screen, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AssetFilterBar from '../asset-filter-bar'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const baseProps = {
  keyword: '',
  category: undefined,
  tags: [] as string[],
  onKeywordChange: vi.fn(),
  onCategoryChange: vi.fn(),
  onTagsChange: vi.fn(),
}

describe('AssetFilterBar', () => {
  it('debounces search input by 300ms', () => {
    vi.useFakeTimers()
    const onKeywordChange = vi.fn()
    render(<AssetFilterBar {...baseProps} onKeywordChange={onKeywordChange} />)
    const input = screen.getByPlaceholderText('filters.searchPlaceholder')
    fireEvent.change(input, { target: { value: 'hello' } })
    expect(onKeywordChange).not.toHaveBeenCalled()
    act(() => { vi.advanceTimersByTime(300) })
    expect(onKeywordChange).toHaveBeenCalledWith('hello')
    vi.useRealTimers()
  })

  it('adds tag on Enter', async () => {
    const onTagsChange = vi.fn()
    render(<AssetFilterBar {...baseProps} onTagsChange={onTagsChange} />)
    const input = screen.getByPlaceholderText('filters.tagsPlaceholder')
    await userEvent.type(input, 'newtag{Enter}')
    expect(onTagsChange).toHaveBeenCalledWith(['newtag'])
  })

  it('removes tag when chip X is clicked', () => {
    const onTagsChange = vi.fn()
    render(<AssetFilterBar {...baseProps} tags={['a', 'b']} onTagsChange={onTagsChange} />)
    const removeBtn = screen.getByLabelText(/remove a/i)
    fireEvent.click(removeBtn)
    expect(onTagsChange).toHaveBeenCalledWith(['b'])
  })

  it('ignores duplicate tag add', async () => {
    const onTagsChange = vi.fn()
    render(<AssetFilterBar {...baseProps} tags={['a']} onTagsChange={onTagsChange} />)
    const input = screen.getByPlaceholderText('filters.tagsPlaceholder')
    await userEvent.type(input, 'a{Enter}')
    expect(onTagsChange).not.toHaveBeenCalled()
  })

  it('does not add empty tag', async () => {
    const onTagsChange = vi.fn()
    render(<AssetFilterBar {...baseProps} onTagsChange={onTagsChange} />)
    const input = screen.getByPlaceholderText('filters.tagsPlaceholder')
    await userEvent.type(input, '   {Enter}')
    expect(onTagsChange).not.toHaveBeenCalled()
  })
})
```

**Step 2: Run — FAIL.**

**Step 3: Implement**

```tsx
// _components/asset-filter-bar.tsx
'use client'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RiCloseLine } from '@remixicon/react'

type Props = {
  keyword: string
  category: string | undefined
  tags: string[]
  onKeywordChange: (v: string) => void
  onCategoryChange: (v: string | undefined) => void
  onTagsChange: (v: string[]) => void
}

const DEBOUNCE_MS = 300

export default function AssetFilterBar({
  keyword, category, tags,
  onKeywordChange, onCategoryChange, onTagsChange,
}: Props) {
  const { t } = useTranslation('assetLibrary')
  const [localKeyword, setLocalKeyword] = useState(keyword)
  const [tagInput, setTagInput] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => { setLocalKeyword(keyword) }, [keyword])

  const handleKeywordChange = (v: string) => {
    setLocalKeyword(v)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => onKeywordChange(v), DEBOUNCE_MS)
  }

  const addTag = () => {
    const v = tagInput.trim()
    if (!v || tags.includes(v)) {
      setTagInput('')
      return
    }
    onTagsChange([...tags, v])
    setTagInput('')
  }

  const removeTag = (t: string) => onTagsChange(tags.filter(x => x !== t))

  return (
    <div className="my-3 flex flex-wrap items-center gap-3">
      <input
        type="text"
        value={localKeyword}
        onChange={e => handleKeywordChange(e.target.value)}
        placeholder={t('filters.searchPlaceholder')}
        className="h-9 flex-1 min-w-[240px] rounded-md border border-divider-subtle px-3 text-sm focus:outline-none focus:border-primary-600"
      />
      <input
        type="text"
        value={category ?? ''}
        onChange={e => onCategoryChange(e.target.value || undefined)}
        placeholder={t('filters.categoryPlaceholder')}
        className="h-9 w-40 rounded-md border border-divider-subtle px-3 text-sm focus:outline-none focus:border-primary-600"
      />
      <div className="flex items-center gap-1.5">
        {tags.map(tag => (
          <span key={tag} className="inline-flex items-center gap-1 rounded-full bg-background-section px-2 py-1 text-xs">
            {tag}
            <button
              type="button"
              aria-label={`remove ${tag}`}
              onClick={() => removeTag(tag)}
              className="text-text-tertiary hover:text-text-primary"
            >
              <RiCloseLine className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={tagInput}
          onChange={e => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              addTag()
            }
          }}
          placeholder={t('filters.tagsPlaceholder')}
          className="h-9 w-44 rounded-md border border-divider-subtle px-3 text-sm focus:outline-none focus:border-primary-600"
        />
      </div>
    </div>
  )
}
```

**Step 4: Run — PASS.**

**Step 5: Lint + commit**

```bash
cd web && pnpm lint:fix app/\(creatorLayout\)/creator-asset-library/_components/asset-filter-bar.tsx app/\(creatorLayout\)/creator-asset-library/_components/__tests__/asset-filter-bar.spec.tsx
git add web/app/\(creatorLayout\)/creator-asset-library/_components/asset-filter-bar.tsx \
        web/app/\(creatorLayout\)/creator-asset-library/_components/__tests__/asset-filter-bar.spec.tsx
git commit -m "feat(asset-library/web): AssetFilterBar component"
```

---

### Task 11：Pagination

**Files:**
- Create: `_components/pagination.tsx`
- Test: `_components/__tests__/pagination.spec.tsx`

**Step 1: Failing tests**

Cover:
1. Returns null when total <= limit
2. Renders prev/next buttons + "Page X of Y"
3. Prev disabled on page 1; Next disabled when !hasMore
4. Click prev/next calls onChange with correct value

Implement, lint, commit. Code is mechanical — keep simple.

```tsx
// pagination.tsx
'use client'
import { useTranslation } from 'react-i18next'

type Props = {
  page: number
  total: number
  limit: number
  hasMore: boolean
  onChange: (page: number) => void
}

export default function Pagination({ page, total, limit, hasMore, onChange }: Props) {
  const { t } = useTranslation('assetLibrary')
  if (total <= limit) return null
  const totalPages = Math.max(1, Math.ceil(total / limit))
  return (
    <div className="mt-4 flex items-center justify-end gap-2 text-sm">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        className="rounded-md border border-divider-subtle px-3 py-1.5 disabled:opacity-50"
      >
        {t('pagination.previous')}
      </button>
      <span className="text-text-tertiary">
        {t('pagination.page', { current: page, total: totalPages })}
      </span>
      <button
        type="button"
        disabled={!hasMore}
        onClick={() => onChange(page + 1)}
        className="rounded-md border border-divider-subtle px-3 py-1.5 disabled:opacity-50"
      >
        {t('pagination.next')}
      </button>
    </div>
  )
}
```

Commit: `feat(asset-library/web): Pagination component`

---

### Task 12：AssetCard + AssetGrid

**Files:**
- Create: `_components/asset-card.tsx`
- Create: `_components/asset-grid.tsx`
- Test: `_components/__tests__/asset-grid.spec.tsx`

**Step 1: Failing tests for AssetGrid**

Cover:
1. `loading=true` renders 6 skeletons
2. `items=[]` + `loading=false` renders empty state with i18n key
3. Renders one card per item; card click calls `onSelect(item.id)`
4. Image item: shows `<img>` with `signed_url` as src
5. Video item: shows `cover_url` background + duration badge `15.2s`
6. AssetCard with no `signed_url` falls back to icon placeholder

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AssetGrid from '../asset-grid'
import type { AssetLibraryItem } from '@/contract/console/asset-library'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const makeItem = (override: Partial<AssetLibraryItem> = {}): AssetLibraryItem => ({
  id: 'a1', tenant_id: 't', asset_type: 'image',
  name: '产品图', description: null, tags: [], category: null,
  upload_file_id: 'u1', cover_url: null, signed_url: 'https://cdn/x.png',
  duration: null, width: 640, height: 480, file_size: 1234,
  content: null, prompt_variables: [],
  created_by: { id: 'u', name: '张三', avatar: null },
  created_at: 0, updated_at: 0,
  ...override,
})

describe('AssetGrid', () => {
  it('renders skeletons while loading', () => {
    render(<AssetGrid items={[]} loading onSelect={() => {}} />)
    expect(screen.getAllByTestId('asset-skeleton')).toHaveLength(6)
  })

  it('shows empty state when no items', () => {
    render(<AssetGrid items={[]} loading={false} onSelect={() => {}} />)
    expect(screen.getByText('empty.all')).toBeInTheDocument()
  })

  it('calls onSelect when card is clicked', () => {
    const fn = vi.fn()
    render(<AssetGrid items={[makeItem()]} loading={false} onSelect={fn} />)
    fireEvent.click(screen.getByRole('button', { name: /产品图/ }))
    expect(fn).toHaveBeenCalledWith('a1')
  })

  it('renders <img> for image with signed_url', () => {
    render(<AssetGrid items={[makeItem()]} loading={false} onSelect={() => {}} />)
    expect(screen.getByRole('img', { name: '产品图' })).toHaveAttribute('src', 'https://cdn/x.png')
  })

  it('renders duration badge for video', () => {
    const v = makeItem({ asset_type: 'video', duration: 15.2, cover_url: 'https://cdn/c.jpg' })
    render(<AssetGrid items={[v]} loading={false} onSelect={() => {}} />)
    expect(screen.getByText(/15\.2s/)).toBeInTheDocument()
  })
})
```

**Step 2: Implement** (concise, see design doc §6 for visual spec).

```tsx
// asset-card.tsx
import { RiImage2Line, RiPlayCircleLine } from '@remixicon/react'
import type { AssetLibraryItem } from '@/contract/console/asset-library'

type Props = {
  item: AssetLibraryItem
  onSelect: (id: string) => void
}

export default function AssetCard({ item, onSelect }: Props) {
  const isVideo = item.asset_type === 'video'
  const imgSrc = isVideo ? item.cover_url : item.signed_url
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      aria-label={item.name}
      className="group relative aspect-[4/3] overflow-hidden rounded-lg border border-divider-subtle bg-background-section text-left"
    >
      {imgSrc
        ? <img src={imgSrc} alt={item.name} className="h-full w-full object-cover" />
        : (
          <div className="flex h-full w-full items-center justify-center text-text-tertiary">
            <RiImage2Line className="h-10 w-10" />
          </div>
        )}
      {isVideo && (
        <>
          <RiPlayCircleLine className="absolute inset-0 m-auto h-12 w-12 text-white opacity-0 transition-opacity group-hover:opacity-90" />
          {item.duration != null && (
            <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-[11px] text-white">
              {item.duration.toFixed(1)}s
            </span>
          )}
        </>
      )}
      <div className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent p-2 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
        {item.name}
      </div>
    </button>
  )
}
```

```tsx
// asset-grid.tsx
'use client'
import { useTranslation } from 'react-i18next'
import AssetCard from './asset-card'
import type { AssetLibraryItem } from '@/contract/console/asset-library'

type Props = {
  items: AssetLibraryItem[]
  loading: boolean
  onSelect: (id: string) => void
}

export default function AssetGrid({ items, loading, onSelect }: Props) {
  const { t } = useTranslation('assetLibrary')
  if (loading) {
    return (
      <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} data-testid="asset-skeleton" className="aspect-[4/3] animate-pulse rounded-lg bg-background-section" />
        ))}
      </div>
    )
  }
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-tertiary">
        <p>{t('empty.all')}</p>
      </div>
    )
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
      {items.map(item => <AssetCard key={item.id} item={item} onSelect={onSelect} />)}
    </div>
  )
}
```

**Step 3: PASS, lint, commit.**

Commit: `feat(asset-library/web): AssetGrid + AssetCard components`

---

### Task 13：AssetRow + AssetList

**Files:**
- Create: `_components/asset-row.tsx`
- Create: `_components/asset-list.tsx`
- Test: `_components/__tests__/asset-list.spec.tsx`

**Step 1: Failing tests** (mirror Task 12 structure)

Cover:
1. Loading skeletons (5 rows)
2. Empty state
3. Click row → onSelect(id)
4. Audio row shows duration formatted; prompt row shows content preview truncated to 50 chars
5. Tags rendered as chips
6. Created_by name shown

**Step 2: Implement**

```tsx
// asset-row.tsx
import { RiFileTextLine, RiMusicLine } from '@remixicon/react'
import type { AssetLibraryItem } from '@/contract/console/asset-library'

const PREVIEW_LIMIT = 50

const formatDuration = (seconds: number | null) => {
  if (seconds == null) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

type Props = {
  item: AssetLibraryItem
  onSelect: (id: string) => void
}

export default function AssetRow({ item, onSelect }: Props) {
  const isPrompt = item.asset_type === 'prompt'
  const Icon = isPrompt ? RiFileTextLine : RiMusicLine
  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className="grid w-full grid-cols-[24px_1fr_120px_120px_120px_120px] items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm hover:bg-background-section"
    >
      <Icon className="h-5 w-5 text-text-tertiary" />
      <div className="min-w-0">
        <div className="truncate font-medium text-text-primary">{item.name}</div>
        {isPrompt && item.content && (
          <div className="truncate text-xs text-text-tertiary">
            {item.content.length > PREVIEW_LIMIT
              ? `${item.content.slice(0, PREVIEW_LIMIT)}…`
              : item.content}
          </div>
        )}
      </div>
      <div className="text-text-tertiary">{item.asset_type}</div>
      <div className="text-text-tertiary">{!isPrompt && formatDuration(item.duration)}</div>
      <div className="flex flex-wrap gap-1">
        {item.tags.slice(0, 3).map(t => (
          <span key={t} className="rounded-full bg-background-section px-1.5 py-0.5 text-xs">{t}</span>
        ))}
      </div>
      <div className="truncate text-text-tertiary">{item.created_by?.name ?? ''}</div>
    </button>
  )
}
```

```tsx
// asset-list.tsx
'use client'
import { useTranslation } from 'react-i18next'
import AssetRow from './asset-row'
import type { AssetLibraryItem } from '@/contract/console/asset-library'

type Props = {
  items: AssetLibraryItem[]
  loading: boolean
  onSelect: (id: string) => void
}

export default function AssetList({ items, loading, onSelect }: Props) {
  const { t } = useTranslation('assetLibrary')
  if (loading) {
    return (
      <div className="flex flex-col gap-1">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} data-testid="asset-skeleton-row" className="h-12 animate-pulse rounded-md bg-background-section" />
        ))}
      </div>
    )
  }
  if (items.length === 0)
    return <div className="py-16 text-center text-text-tertiary">{t('empty.all')}</div>
  return (
    <div className="flex flex-col gap-1">
      {items.map(item => <AssetRow key={item.id} item={item} onSelect={onSelect} />)}
    </div>
  )
}
```

Commit: `feat(asset-library/web): AssetList + AssetRow components`

---

## Phase 4：上传 + 提示词创建

### Task 14：UploadDropzone

**Files:**
- Create: `_components/upload-dropzone.tsx`
- Test: `_components/__tests__/upload-dropzone.spec.tsx`

**Step 1: Failing tests**

Cover:
1. Drag idle: shows `dropzoneIdle` text
2. Drag enter: shows `dropzoneActive` text
3. Drop file with allowed MIME → calls upload mutation per file (mocked)
4. Drop file with disallowed MIME → toast error, no upload
5. Drop file > 200MB → toast error
6. Multi-file drop: all start; each chip shows progress; chip auto-clears on success
7. Upload failure: chip turns red, X button clears it

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import UploadDropzone from '../upload-dropzone'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, v?: any) => v ? `${k}:${JSON.stringify(v)}` : k }),
}))

const mockMutate = vi.fn()
vi.mock('@/service/use-asset-library', () => ({
  useUploadAssetFile: () => ({
    mutateAsync: (...args: any[]) => mockMutate(...args),
  }),
}))

const mockToast = vi.fn()
vi.mock('@/app/components/base/toast', () => ({
  default: { notify: (...args: any[]) => mockToast(...args) },
}))

describe('UploadDropzone', () => {
  it('rejects non-whitelisted MIME', async () => {
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)
    const file = new File(['x'], 'x.bmp', { type: 'image/bmp' })
    const dropzone = screen.getByTestId('asset-dropzone')
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } })
    await waitFor(() => expect(mockToast).toHaveBeenCalled())
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('starts upload for allowed MIME', async () => {
    mockMutate.mockResolvedValue({})
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)
    const file = new File(['x'], 'x.png', { type: 'image/png' })
    fireEvent.drop(screen.getByTestId('asset-dropzone'), { dataTransfer: { files: [file] } })
    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
    const arg = mockMutate.mock.calls[0][0]
    expect(arg.asset_type).toBe('image')
    expect(arg.file).toBe(file)
  })

  it('infers asset_type from MIME on multi-MIME drop', async () => {
    mockMutate.mockResolvedValue({})
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)
    const audio = new File(['x'], 'x.mp3', { type: 'audio/mpeg' })
    fireEvent.drop(screen.getByTestId('asset-dropzone'), { dataTransfer: { files: [audio] } })
    await waitFor(() => expect(mockMutate).toHaveBeenCalled())
    expect(mockMutate.mock.calls[0][0].asset_type).toBe('audio')
  })

  it('rejects file > 200MB', async () => {
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)
    const big = new File([new Uint8Array(0)], 'x.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 201 * 1024 * 1024 })
    fireEvent.drop(screen.getByTestId('asset-dropzone'), { dataTransfer: { files: [big] } })
    await waitFor(() => expect(mockToast).toHaveBeenCalled())
    expect(mockMutate).not.toHaveBeenCalled()
  })
})
```

**Step 2: Implement**

```tsx
// upload-dropzone.tsx
'use client'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RiCloseLine, RiUploadCloud2Line } from '@remixicon/react'
import { useUploadAssetFile } from '@/service/use-asset-library'
import Toast from '@/app/components/base/toast'
import type { AssetType } from '@/contract/console/asset-library'

const MAX_SIZE_BYTES = 200 * 1024 * 1024

const MIME_TYPE_MAP: Record<string, AssetType> = {
  'image/jpeg': 'image',
  'image/png': 'image',
  'image/webp': 'image',
  'image/gif': 'image',
  'video/mp4': 'video',
  'video/quicktime': 'video',
  'audio/mpeg': 'audio',
  'audio/mp4': 'audio',
  'audio/wav': 'audio',
}

type ProgressItem = {
  id: string
  filename: string
  percent: number
  error?: string
}

type Props = {
  defaultAssetType: 'image' | 'audio' | 'video'
  onUploaded: () => void
}

export default function UploadDropzone({ onUploaded }: Props) {
  const { t } = useTranslation('assetLibrary')
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<ProgressItem[]>([])
  const upload = useUploadAssetFile()

  const updateProgress = (id: string, patch: Partial<ProgressItem>) => {
    setProgress(prev => prev.map(p => p.id === id ? { ...p, ...patch } : p))
  }

  const removeProgress = (id: string) => {
    setProgress(prev => prev.filter(p => p.id !== id))
  }

  const startUpload = useCallback(async (file: File) => {
    if (file.size > MAX_SIZE_BYTES) {
      Toast.notify({ type: 'error', message: t('upload.fileTooLarge') })
      return
    }
    const assetType = MIME_TYPE_MAP[file.type]
    if (!assetType) {
      Toast.notify({
        type: 'error',
        message: t('upload.unsupportedMime', { mime: file.type || 'unknown' }),
      })
      return
    }
    const id = `${file.name}-${Date.now()}-${Math.random()}`
    setProgress(prev => [...prev, { id, filename: file.name, percent: 0 }])
    try {
      await upload.mutateAsync({
        file,
        asset_type: assetType,
        name: file.name,
        onProgress: percent => updateProgress(id, { percent }),
      })
      removeProgress(id)
      onUploaded()
    } catch (err: unknown) {
      const reason = err instanceof Error ? err.message : 'upload failed'
      updateProgress(id, { error: reason })
    }
  }, [t, upload, onUploaded])

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    Array.from(e.dataTransfer.files).forEach(startUpload)
  }

  return (
    <div className="my-3">
      <label
        data-testid="asset-dropzone"
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex h-28 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed transition-colors ${
          dragging ? 'border-primary-600 bg-primary-50' : 'border-divider-subtle bg-background-section'
        }`}
      >
        <input
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            Array.from(e.target.files ?? []).forEach(startUpload)
            e.currentTarget.value = ''
          }}
        />
        <RiUploadCloud2Line className="mb-1 h-6 w-6 text-text-tertiary" />
        <span className="text-sm text-text-tertiary">
          {dragging ? t('upload.dropzoneActive') : t('upload.dropzoneIdle')}
        </span>
      </label>
      {progress.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {progress.map(p => (
            <div
              key={p.id}
              className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs ${
                p.error ? 'bg-state-destructive-50 text-state-destructive' : 'bg-background-section'
              }`}
            >
              <span className="max-w-[160px] truncate">
                {p.error
                  ? t('upload.uploadFailed', { reason: p.error })
                  : t('upload.uploading', { filename: p.filename })}
              </span>
              <span>{p.error ? '' : `${p.percent}%`}</span>
              {p.error && (
                <button type="button" onClick={() => removeProgress(p.id)} aria-label="dismiss">
                  <RiCloseLine className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

> Verify the toast import path matches what Dify uses. If `@/app/components/base/toast` is wrong, fix it (check a sibling component's import).

**Step 3: PASS, lint, commit**

Commit: `feat(asset-library/web): UploadDropzone with drag/drop + multi-file progress`

---

### Task 15：PromptDialog

**Files:**
- Create: `_components/prompt-dialog.tsx`
- Test: `_components/__tests__/prompt-dialog.spec.tsx`

**Step 1: Failing tests**

Cover:
1. Initially closed; clicking trigger opens dialog
2. Submitting with empty name shows validation error
3. Submitting with empty content shows validation error
4. Adding/removing variables works
5. Successful submit: calls mutation with correct payload, closes dialog, calls onCreated
6. 422 InvalidPromptVariablesError: dialog stays open, shows error

**Step 2: Implement** (~150 lines, key parts):

```tsx
// prompt-dialog.tsx
'use client'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RiAddLine, RiCloseLine } from '@remixicon/react'
import { useCreatePromptAsset } from '@/service/use-asset-library'
import type { PromptVariable } from '@/contract/console/asset-library'
import Toast from '@/app/components/base/toast'

// Use Dify's overlay primitive: see docs/overlay-migration.md
// Likely: import { Modal } from '@/app/components/base/ui/modal'  (verify the actual primitive)

type Props = { onCreated: () => void }

export default function PromptDialog({ onCreated }: Props) {
  const { t } = useTranslation('assetLibrary')
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [category, setCategory] = useState('')
  const [variables, setVariables] = useState<PromptVariable[]>([])
  const [error, setError] = useState<string | null>(null)
  const create = useCreatePromptAsset()

  const reset = () => {
    setName(''); setContent(''); setDescription(''); setTags([]); setTagInput('')
    setCategory(''); setVariables([]); setError(null)
  }

  const submit = async () => {
    if (!name.trim()) { setError(t('prompt.validation.nameRequired')); return }
    if (!content.trim()) { setError(t('prompt.validation.contentRequired')); return }
    setError(null)
    try {
      await create.mutateAsync({
        name: name.trim(),
        content,
        prompt_variables: variables,
        description: description || null,
        tags,
        category: category || null,
      })
      Toast.notify({ type: 'success', message: t('detail.savedToast') })
      onCreated()
      setOpen(false)
      reset()
    } catch (err: unknown) {
      const reason = err instanceof Error ? err.message : 'unknown'
      setError(t('errors.validationFailed', { reason }))
    }
  }

  const addVariable = () => setVariables([
    ...variables,
    { name: '', type: 'string', default: null, description: null },
  ])
  const removeVariable = (i: number) => setVariables(variables.filter((_, idx) => idx !== i))
  const updateVariable = (i: number, patch: Partial<PromptVariable>) =>
    setVariables(variables.map((v, idx) => idx === i ? { ...v, ...patch } : v))

  // Simplified inline modal — replace with the project's overlay primitive
  return (
    <>
      <button type="button"
        onClick={() => setOpen(true)}
        className="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white">
        {t('prompt.newButton')}
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-[640px] max-h-[90vh] overflow-y-auto rounded-lg bg-background-default p-6">
            <h2 className="mb-4 text-lg font-semibold">{t('prompt.dialogTitle')}</h2>
            {/* form fields ... see detail in design doc §6 */}
            {/* name / content / description / tags / category / variables list / addVariable */}
            {error && <p className="text-sm text-state-destructive">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => { setOpen(false); reset() }}
                className="rounded-md border border-divider-subtle px-3 py-1.5 text-sm">
                {t('prompt.cancel')}
              </button>
              <button type="button" onClick={submit} disabled={create.isPending}
                className="rounded-md bg-primary-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
                {t('prompt.create')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
```

**Note:** Per `web/CLAUDE.md` — use overlay primitives from `@/app/components/base/ui/*`. **Look at how `social-publish` or another recent component opens a dialog**, replicate that pattern instead of inline `<div className="fixed">`. The above is a fallback only.

**Step 3: PASS, lint, commit**

Commit: `feat(asset-library/web): PromptDialog component`

---

## Phase 5：详情 drawer

### Task 16：DeleteConfirmDialog

**Files:**
- Create: `_components/delete-confirm-dialog.tsx`
- Test: `_components/__tests__/delete-confirm-dialog.spec.tsx`

Look for an existing confirm dialog primitive in the project (`@/app/components/base/ui/`) and wrap it. Tests cover: open=false → not rendered; click confirm → onConfirm; click cancel → onCancel.

Commit: `feat(asset-library/web): DeleteConfirmDialog component`

---

### Task 17：AssetDetailDrawer

**Files:**
- Create: `_components/asset-detail-drawer.tsx`
- Create: `_components/asset-preview.tsx` (4 type-specific previews)
- Test: `_components/__tests__/asset-detail-drawer.spec.tsx`

**Step 1: Failing tests**

Cover:
1. `assetId={null}` → renders nothing
2. With assetId → fetches detail (mocked) and renders preview + form
3. Editing a field marks `dirty` (Save button enabled)
4. Save button: calls `usePatchAsset.mutate({ asset_id, body })`, calls onMutated, dirty=false
5. Delete button: opens confirm dialog
6. Confirm delete: calls `useDeleteAsset.mutate(id)`, closes drawer, calls onMutated
7. Image preview: `<img>` from signed_url
8. Video preview: `<video controls>` from signed_url
9. Audio preview: `<audio controls>` from signed_url
10. Prompt preview: textarea showing content + Copy button (clipboard write)

**Step 2: Implement** — split preview component cleanly:

```tsx
// asset-preview.tsx
import { useTranslation } from 'react-i18next'
import Toast from '@/app/components/base/toast'
import type { AssetLibraryItem } from '@/contract/console/asset-library'

export default function AssetPreview({ asset }: { asset: AssetLibraryItem }) {
  const { t } = useTranslation('assetLibrary')
  const url = asset.signed_url ?? ''

  if (asset.asset_type === 'image')
    return <img src={url} alt={asset.name} className="max-h-full max-w-full object-contain" />

  if (asset.asset_type === 'video')
    return <video controls src={url} className="max-h-full max-w-full" />

  if (asset.asset_type === 'audio')
    return <audio controls src={url} className="w-full" />

  // prompt
  const copy = async () => {
    await navigator.clipboard.writeText(asset.content ?? '')
    Toast.notify({ type: 'success', message: t('detail.copiedToast') })
  }
  return (
    <div className="flex h-full flex-col gap-2">
      <pre className="flex-1 overflow-auto rounded-md bg-background-section p-3 text-sm">
        {asset.content ?? ''}
      </pre>
      <button type="button" onClick={copy}
        className="self-end rounded-md border border-divider-subtle px-3 py-1.5 text-sm">
        {t('detail.copyContent')}
      </button>
    </div>
  )
}
```

Drawer body uses Dify's drawer primitive — verify by reading sibling component (e.g. `web/app/components/datasets/.../drawer.tsx`).

**Step 3: PASS, lint, commit**

Commit: `feat(asset-library/web): AssetDetailDrawer with edit/delete`

---

## Phase 6：组装 + 验收

### Task 18：Assemble AssetLibraryPage

**Files:**
- Modify: `_components/asset-library-page.tsx` (replace placeholder)

**Step 1: Replace placeholder with full implementation** (see design doc §5.3)

```tsx
'use client'

import { useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useTranslation } from 'react-i18next'
import { useAssetLibraryList } from '@/service/use-asset-library'
import type { AssetType } from '@/contract/console/asset-library'
import AssetTabs, { type TabValue } from './asset-tabs'
import AssetFilterBar from './asset-filter-bar'
import AssetGrid from './asset-grid'
import AssetList from './asset-list'
import UploadDropzone from './upload-dropzone'
import PromptDialog from './prompt-dialog'
import AssetDetailDrawer from './asset-detail-drawer'
import Pagination from './pagination'

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

  const detailAssetId = sp.get('asset_id')
  const setDetailAssetId = (id: string | null) => {
    const next = new URLSearchParams(sp.toString())
    if (id) next.set('asset_id', id)
    else next.delete('asset_id')
    router.replace(`${pathname}?${next.toString()}`)
  }

  const list = useAssetLibraryList({
    type: tab === 'all' ? undefined : tab,
    keyword: keyword || undefined,
    category,
    tags: tags.length ? tags : undefined,
    page,
    limit: 20,
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
        keyword={keyword}
        category={category}
        tags={tags}
        onKeywordChange={(v) => { setKeyword(v); setPage(1) }}
        onCategoryChange={(v) => { setCategory(v); setPage(1) }}
        onTagsChange={(v) => { setTags(v); setPage(1) }}
      />

      {tab !== 'prompt' && (
        <UploadDropzone
          defaultAssetType={tab === 'all' ? 'image' : (tab as 'image' | 'audio' | 'video')}
          onUploaded={() => list.refetch()}
        />
      )}

      {isGridMode
        ? <AssetGrid items={list.data?.data ?? []} loading={list.isLoading} onSelect={setDetailAssetId} />
        : <AssetList items={list.data?.data ?? []} loading={list.isLoading} onSelect={setDetailAssetId} />}

      <Pagination
        page={page}
        total={list.data?.total ?? 0}
        limit={20}
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

**Step 2: Type-check + lint**

```bash
cd web
pnpm lint:fix app/\(creatorLayout\)/creator-asset-library/_components/asset-library-page.tsx
pnpm type-check:tsgo
```

**Step 3: Commit**

```bash
git add web/app/\(creatorLayout\)/creator-asset-library/_components/asset-library-page.tsx
git commit -m "feat(asset-library/web): assemble AssetLibraryPage"
```

---

### Task 19：Run full test suite + coverage

**Step 1: Run vitest**

```bash
cd web && pnpm vitest run \
  contract/console/asset-library.ts \
  service/asset-library.spec.ts \
  service/use-asset-library.spec.ts \
  app/\(creatorLayout\)/creator-asset-library/
```

Expected: All tests pass.

**Step 2: Coverage check**

```bash
cd web && pnpm vitest run --coverage \
  service/asset-library.spec.ts \
  service/use-asset-library.spec.ts \
  app/\(creatorLayout\)/creator-asset-library/
```

Verify ≥ 80% coverage on new modules.

**Step 3: Lint + type-check entire scope**

```bash
cd web
pnpm lint:fix
pnpm type-check:tsgo
```

Fix any new findings.

**Step 4: Commit any lint/format fixes**

```bash
git add -A
git commit -m "chore(asset-library/web): final lint pass" || true
```

---

### Task 20：Manual smoke (handed to user)

**Steps for user to run on their dev environment:**

```bash
cd web && pnpm dev
```

Visit `http://localhost:3000/creator-asset-library`. Verify:

1. Sidebar "素材库" item appears + active when on this page
2. All tab switches work (全部 / 图片 / 视频 / 音频 / 提示词)
3. Drag a PNG into the dropzone → progress chip appears → completes → image card appears in grid
4. Click image card → drawer opens with preview + form
5. Edit name in drawer → Save → toast → list updates
6. Delete from drawer → confirm → drawer closes + list updates
7. Switch to 提示词 tab → click 新建提示词 → fill form → submit → row appears
8. Search "test" in search box → list filters
9. Add a tag chip → list filters by tag
10. Refresh page with `?asset_id=xxx` in URL → drawer auto-opens

**Stop server after verification.**

If any step fails, capture the specific failure and report.

---

## 风险与回滚

- **Contract path mismatch (404)**：`base.route.path` 必须不带 `/console/api` 前缀（client 自动加）。如果手测看到 404，确认 contract 路径与后端 blueprint 注册的路径一致。
- **`signed_url` 实际无法访问**：后端 task 16 应已确认。如果浏览器拿不到图片，先回到后端 fields/serializer 调试。
- **i18n key 缺失**：用 `t('xxx.yyy')` 但 JSON 没这个 key 时，i18next 默认返回 key 字符串本身。测试里都断言 key 而非翻译值，runtime 漏 key 通过手测捕获。
- **基础组件实测样式不合**：本 plan 优先功能正确性，UI 细节（间距、颜色、动画）由 task 20 手测后再 polish；不阻塞 MVP。

## YAGNI 提醒

- ❌ 选择器弹窗（嵌入 social-publish）
- ❌ 标签自动补全（候选 tag 端点）
- ❌ 批量选择 / 批量删除
- ❌ 上传断点续传 / 大文件分片
- ❌ 视频实时压缩 / 二次封面选择
- ❌ E2E Playwright（先靠单测）

---

## 总览

**20 个 task，6 个 phase，预计 4-5 天。**

| Phase | Tasks | 工时估计 |
|---|---|---|
| 1 契约 + Service | 1-4 | 半天 |
| 2 i18n + sidebar + 入口 | 5-8 | 半天 |
| 3 基础组件 | 9-13 | 1 天 |
| 4 上传 + 提示词 | 14-15 | 1 天 |
| 5 详情 drawer | 16-17 | 1 天 |
| 6 组装 + 验收 | 18-20 | 半天 |

每个 task TDD 红→绿→commit，单测覆盖 ≥ 80%，符合 `web/CLAUDE.md` 强制约束。
