import { get, patch, post } from '@/service/base'

export type CreatorTaskStatus = 'pending' | 'running' | 'waiting_input' | 'completed' | 'failed'

export type CreatorTask = {
  id: string
  account_id: string
  tenant_id: string
  app_id: string
  installed_app_id: string
  conversation_id: string | null
  workflow_run_id: string | null
  status: CreatorTaskStatus
  title: string | null
  created_at: string
  updated_at: string
}

export type CreatorTaskListResponse = {
  tasks: CreatorTask[]
  total: number
  in_progress_count: number
}

export type CreateTaskPayload = {
  app_id: string
  installed_app_id: string
  conversation_id?: string
  workflow_run_id?: string
  title?: string
}

export type UpdateTaskPayload = {
  status: CreatorTaskStatus
  last_updated_at?: string
}

export const listCreatorTasks = (): Promise<CreatorTaskListResponse> =>
  get<CreatorTaskListResponse>('/creator/tasks')

export const createCreatorTask = (payload: CreateTaskPayload): Promise<CreatorTask> =>
  post<CreatorTask>('/creator/tasks', { body: payload })

export const getCreatorTask = (taskId: string): Promise<CreatorTask> =>
  get<CreatorTask>(`/creator/tasks/${taskId}`)

export const updateCreatorTask = (taskId: string, payload: UpdateTaskPayload): Promise<CreatorTask> =>
  patch<CreatorTask>(`/creator/tasks/${taskId}`, { body: payload })
