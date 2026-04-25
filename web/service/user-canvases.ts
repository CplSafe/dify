import { del, get, patch, post } from '@/service/base'

const CANVASES_URL = '/creator/canvases'
const canvasUrl = (canvasId: string) => `${CANVASES_URL}/${canvasId}`

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

export type CanvasSnapshotNode = {
  node_id: string
  node_type: string
  title: string
  predecessor_node_id: string | null
  inputs: Record<string, unknown> | null
  outputs: Record<string, unknown> | null
  status: string
  error: string | null
}

export type CanvasSnapshotResponse = {
  canvas: UserCanvas
  nodes: CanvasSnapshotNode[]
  // FIX8: true when the underlying workflow_run has been GC'd; nodes
  // will be empty and the UI should show an explicit "snapshot expired"
  // state instead of a blank successful canvas.
  expired: boolean
}

export const listUserCanvases = (params?: { app_id?: string }) =>
  get<UserCanvasListResponse>(CANVASES_URL, { params })

export const createUserCanvas = (body: CreateUserCanvasBody) =>
  post<UserCanvas>(CANVASES_URL, { body })

export const renameUserCanvas = (canvasId: string, title: string) =>
  patch<UserCanvas>(canvasUrl(canvasId), { body: { title } })

export const deleteUserCanvas = (canvasId: string) =>
  del<{ deleted: number }>(canvasUrl(canvasId))

export const getUserCanvasSnapshot = (canvasId: string) =>
  get<CanvasSnapshotResponse>(`${canvasUrl(canvasId)}/snapshot`)
