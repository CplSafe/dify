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
  .input(
    type<{
      query?: {
        type?: AssetType
        keyword?: string
        category?: string
        tags?: string[]
        page?: number
        limit?: number
      }
    }>(),
  )
  .output(type<AssetLibraryListResponse>())

export const assetLibraryDetailContract = base
  .route({ method: 'GET', path: '/asset-library/{asset_id}' })
  .input(type<{ params: { asset_id: string } }>())
  .output(type<AssetLibraryItem>())

export const assetLibraryPatchContract = base
  .route({ method: 'PATCH', path: '/asset-library/{asset_id}' })
  .input(
    type<{
      params: { asset_id: string }
      body: {
        name?: string
        description?: string | null
        tags?: string[]
        category?: string | null
        content?: string
        prompt_variables?: PromptVariable[]
      }
    }>(),
  )
  .output(type<AssetLibraryItem>())

export const assetLibraryDeleteContract = base
  .route({ method: 'DELETE', path: '/asset-library/{asset_id}' })
  .input(type<{ params: { asset_id: string } }>())
  .output(type<unknown>())

export const assetLibraryCreatePromptContract = base
  .route({ method: 'POST', path: '/asset-library/prompts' })
  .input(
    type<{
      body: {
        name: string
        content: string
        prompt_variables?: PromptVariable[]
        description?: string | null
        tags?: string[]
        category?: string | null
      }
    }>(),
  )
  .output(type<AssetLibraryItem>())
