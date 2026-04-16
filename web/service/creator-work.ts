import { post } from '@/service/base'

export type CreatorWork = {
  id: string
  account_id: string
  tenant_id: string
  workflow_run_id: string | null
  app_id: string | null
  title: string
  file_key: string | null
  file_type: string
  share_status: string
  output_data: string | null
  created_at: string
  updated_at: string
}

export type CreateWorkPayload = {
  title: string
  file_key: string
  file_type: 'image' | 'video'
  workflow_run_id?: string
  app_id?: string
  output_data?: string
}

const BASE = '/creator/works'

export const createCreatorWork = (
  payload: CreateWorkPayload,
): Promise<CreatorWork> => post<CreatorWork>(BASE, { body: payload })
