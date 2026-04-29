import type { UploadAssetFileBody } from './asset-library'
import type {
  AssetType,
  PromptVariable,
} from '@/contract/console/asset-library'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consoleClient, consoleQuery } from '@/service/client'
import { uploadAssetFile } from './asset-library'

type ListQuery = {
  type?: AssetType
  keyword?: string
  category?: string
  tags?: string[]
  page?: number
  limit?: number
}

type PatchAssetInput = {
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

type CreatePromptAssetBody = {
  name: string
  content: string
  prompt_variables?: PromptVariable[]
  description?: string | null
  tags?: string[]
  category?: string | null
}

const listQueryKey = () => consoleQuery.assetLibrary.list.key()

export const useAssetLibraryList = (query: ListQuery) => {
  return useQuery({
    queryKey: consoleQuery.assetLibrary.list.queryKey({
      input: { query },
    }),
    queryFn: () => consoleClient.assetLibrary.list({ query }),
  })
}

export const useAssetDetail = (assetId: string | null) => {
  return useQuery({
    queryKey: consoleQuery.assetLibrary.detail.queryKey({
      input: { params: { asset_id: assetId ?? '' } },
    }),
    queryFn: () =>
      consoleClient.assetLibrary.detail({
        params: { asset_id: assetId! },
      }),
    enabled: !!assetId,
  })
}

export const usePatchAsset = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: PatchAssetInput) =>
      consoleClient.assetLibrary.patch({
        params: { asset_id: input.asset_id },
        body: input.body,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: listQueryKey(),
      }),
  })
}

export const useDeleteAsset = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (assetId: string) =>
      consoleClient.assetLibrary.delete({
        params: { asset_id: assetId },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: listQueryKey(),
      }),
  })
}

export const useCreatePromptAsset = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: CreatePromptAssetBody) =>
      consoleClient.assetLibrary.createPrompt({ body }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: listQueryKey(),
      }),
  })
}

export const useUploadAssetFile = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: UploadAssetFileBody) => uploadAssetFile(body),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: listQueryKey(),
      }),
  })
}
