import type {
  AuthStartResponse,
  AuthStatusResponse,
  CreateTaskRequest,
  CreateTaskResponse,
  SocialPublishAccount,
  SocialPublishErrorCode,
  SocialPublishPlatform,
  SocialPublishTask,
  SocialPublishTaskStatus,
  TaskStatusResponse,
} from '@/types/social-publish'
import { del, get, post } from './base'

const ACCOUNTS_BASE = '/social-publish/accounts'
const TASKS_BASE = '/social-publish/tasks'

/**
 * Domain-shaped error thrown after parsing the backend's `{code, message,
 * status}` JSON envelope. `service/base` rejects raw `Response` objects for
 * non-401 errors; we normalize them here so callers can branch on `code`
 * without re-implementing the parse in every component.
 */
export class SocialPublishApiError extends Error {
  readonly code: SocialPublishErrorCode | string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'SocialPublishApiError'
    this.code = code
    this.status = status
  }
}

async function withErrorNormalization<T>(promise: Promise<T>): Promise<T> {
  try {
    return await promise
  }
  catch (err) {
    if (!(err instanceof Response))
      throw err
    // Best-effort parse — backend envelope is `{code, message, status}` from `BaseHTTPException`.
    const body = (await err
      .clone()
      .json()
      .catch(() => null)) as { code?: string, message?: string } | null
    throw new SocialPublishApiError(
      body?.code ?? 'social_publish_error',
      body?.message ?? err.statusText ?? 'request failed',
      err.status,
    )
  }
}

export const fetchSocialPublishAccounts = (
  platform?: SocialPublishPlatform,
) => {
  const query = platform ? `?platform=${encodeURIComponent(platform)}` : ''
  return withErrorNormalization(
    get<{ data: SocialPublishAccount[] }>(`${ACCOUNTS_BASE}${query}`),
  )
}

export const startSocialPublishAuth = (body: {
  platform: SocialPublishPlatform
  account_id?: string
}) =>
  withErrorNormalization(
    post<AuthStartResponse>(`${ACCOUNTS_BASE}/auth/start`, { body }),
  )

export const fetchSocialPublishAuthStatus = (sessionId: string) =>
  withErrorNormalization(
    get<AuthStatusResponse>(
      `${ACCOUNTS_BASE}/auth/status/${encodeURIComponent(sessionId)}`,
    ),
  )

export const deleteSocialPublishAccount = (accountId: string) =>
  withErrorNormalization(
    del<{ result: 'success' }>(
      `${ACCOUNTS_BASE}/${encodeURIComponent(accountId)}`,
    ),
  )

// ---------- P2: publish tasks ----------

export const createSocialPublishTask = (body: CreateTaskRequest) =>
  withErrorNormalization(post<CreateTaskResponse>(TASKS_BASE, { body }))

export const fetchSocialPublishTask = (taskId: string) =>
  withErrorNormalization(
    get<TaskStatusResponse>(`${TASKS_BASE}/${encodeURIComponent(taskId)}`),
  )

export const listSocialPublishTasks = (filters?: {
  account_id?: string
  status?: SocialPublishTaskStatus
  limit?: number
}) => {
  const params = new URLSearchParams()
  if (filters?.account_id)
    params.set('account_id', filters.account_id)
  if (filters?.status)
    params.set('status', filters.status)
  if (filters?.limit !== undefined)
    params.set('limit', String(filters.limit))
  const query = params.toString()
  return withErrorNormalization(
    get<{ data: SocialPublishTask[] }>(
      query ? `${TASKS_BASE}?${query}` : TASKS_BASE,
    ),
  )
}
