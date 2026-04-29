import type { ReactNode } from 'react'
import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { uploadAssetFile } from './asset-library'
import { consoleClient } from './client'
import {
  useAssetDetail,
  useAssetLibraryList,
  useCreatePromptAsset,
  useDeleteAsset,
  usePatchAsset,
  useUploadAssetFile,
} from './use-asset-library'

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
      list: {
        queryKey: vi.fn(({ input }: { input: unknown }) => [
          'assetLibrary.list',
          input,
        ]),
        key: vi.fn(() => ['assetLibrary.list']),
      },
      detail: {
        queryKey: vi.fn(({ input }: { input: unknown }) => [
          'assetLibrary.detail',
          input,
        ]),
      },
    },
  },
}))

vi.mock('./asset-library', () => ({
  uploadAssetFile: vi.fn(),
}))

const createAsset = (
  overrides: Partial<AssetLibraryItem> = {},
): AssetLibraryItem => ({
  id: 'asset-1',
  tenant_id: 'tenant-1',
  asset_type: 'image',
  name: 'Hero image',
  description: null,
  tags: [],
  category: null,
  upload_file_id: 'file-1',
  cover_url: null,
  signed_url: 'https://example.com/hero.png',
  duration: null,
  width: 640,
  height: 480,
  file_size: 1024,
  content: null,
  prompt_variables: [],
  created_by: null,
  created_at: 0,
  updated_at: 0,
  ...overrides,
})

const createQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const createWrapper = (queryClient: QueryClient) => {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

const renderAssetHook = <T>(hook: () => T) => {
  const queryClient = createQueryClient()
  return {
    queryClient,
    ...renderHook(hook, {
      wrapper: createWrapper(queryClient),
    }),
  }
}

describe('useAssetLibraryList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should call list with the given query', async () => {
    vi.mocked(consoleClient.assetLibrary.list).mockResolvedValueOnce({
      data: [],
      total: 0,
      page: 1,
      limit: 20,
      has_more: false,
    })

    const { result } = renderAssetHook(() =>
      useAssetLibraryList({ type: 'image', page: 1, limit: 20 }))

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(consoleClient.assetLibrary.list).toHaveBeenCalledWith({
      query: { type: 'image', page: 1, limit: 20 },
    })
  })
})

describe('useAssetDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should not fetch when assetId is null', () => {
    const { result } = renderAssetHook(() => useAssetDetail(null))

    expect(result.current.fetchStatus).toBe('idle')
    expect(consoleClient.assetLibrary.detail).not.toHaveBeenCalled()
  })

  it('should fetch detail when assetId is provided', async () => {
    vi.mocked(consoleClient.assetLibrary.detail).mockResolvedValueOnce(
      createAsset(),
    )

    const { result } = renderAssetHook(() => useAssetDetail('asset-1'))

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(consoleClient.assetLibrary.detail).toHaveBeenCalledWith({
      params: { asset_id: 'asset-1' },
    })
  })
})

describe('asset library mutations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should patch asset metadata and invalidate the list cache', async () => {
    vi.mocked(consoleClient.assetLibrary.patch).mockResolvedValueOnce(
      createAsset({ name: 'Updated' }),
    )
    const { result, queryClient } = renderAssetHook(() => usePatchAsset())
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    await act(async () => {
      await result.current.mutateAsync({
        asset_id: 'asset-1',
        body: { name: 'Updated' },
      })
    })

    expect(consoleClient.assetLibrary.patch).toHaveBeenCalledWith({
      params: { asset_id: 'asset-1' },
      body: { name: 'Updated' },
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['assetLibrary.list'],
    })
  })

  it('should delete an asset and invalidate the list cache', async () => {
    vi.mocked(consoleClient.assetLibrary.delete).mockResolvedValueOnce({})
    const { result, queryClient } = renderAssetHook(() => useDeleteAsset())
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    await act(async () => {
      await result.current.mutateAsync('asset-1')
    })

    expect(consoleClient.assetLibrary.delete).toHaveBeenCalledWith({
      params: { asset_id: 'asset-1' },
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['assetLibrary.list'],
    })
  })

  it('should create a prompt asset and invalidate the list cache', async () => {
    vi.mocked(consoleClient.assetLibrary.createPrompt).mockResolvedValueOnce(
      createAsset({ asset_type: 'prompt', content: 'Write a title' }),
    )
    const { result, queryClient } = renderAssetHook(() =>
      useCreatePromptAsset())
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    await act(async () => {
      await result.current.mutateAsync({
        name: 'Title prompt',
        content: 'Write a title',
      })
    })

    expect(consoleClient.assetLibrary.createPrompt).toHaveBeenCalledWith({
      body: {
        name: 'Title prompt',
        content: 'Write a title',
      },
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['assetLibrary.list'],
    })
  })

  it('should upload a file and invalidate the list cache', async () => {
    vi.mocked(uploadAssetFile).mockResolvedValueOnce(createAsset())
    const { result, queryClient } = renderAssetHook(() => useUploadAssetFile())
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    const file = new File(['x'], 'hero.png', { type: 'image/png' })

    await act(async () => {
      await result.current.mutateAsync({
        file,
        asset_type: 'image',
        name: 'Hero',
      })
    })

    expect(uploadAssetFile).toHaveBeenCalledWith({
      file,
      asset_type: 'image',
      name: 'Hero',
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['assetLibrary.list'],
    })
  })
})
