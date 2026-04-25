import { del, get, patch, post } from '@/service/base'

export type UserCanvas = {
  id: string
  tenant_id: string
  app_id: string
  owner_id: string
  title: string
  source_run_id: string
  created_at: string | null
  updated_at: string | null
}

export type UserCanvasListResponse = {
  data: UserCanvas[]
  total: number
}

export type CreateUserCanvasBody = {
  app_id: string
  title: string
  source_run_id: string
}

const CANVASES_URL = '/creator/canvases'
const canvasUrl = (canvasId: string) => `${CANVASES_URL}/${canvasId}`

export const listUserCanvases = (params?: { app_id?: string }) =>
  get<UserCanvasListResponse>(CANVASES_URL, { params })

export const createUserCanvas = (body: CreateUserCanvasBody) =>
  post<UserCanvas>(CANVASES_URL, { body })

export const renameUserCanvas = (canvasId: string, title: string) =>
  patch<UserCanvas>(canvasUrl(canvasId), { body: { title } })

export const deleteUserCanvas = (canvasId: string) =>
  del<{ deleted: number }>(canvasUrl(canvasId))
