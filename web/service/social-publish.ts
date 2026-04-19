import type {
  AuthStartResponse,
  AuthStatusResponse,
  BatchCreateTaskRequest,
  BatchCreateTaskResponse,
  ChallengeSessionInfo,
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
const CHALLENGE_BASE = `${ACCOUNTS_BASE}/auth/challenge`
const TASKS_BASE = '/social-publish/tasks'

type ErrorEnvelope = { code?: string, message?: string }

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
    const body = (await err
      .clone()
      .json()
      .catch(() => null)) as ErrorEnvelope | null
    throw new SocialPublishApiError(
      body?.code ?? 'social_publish_error',
      body?.message ?? err.statusText ?? 'request failed',
      err.status,
    )
  }
}

const buildQuery = (
  entries: Record<string, string | number | undefined>,
): string => {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(entries)) {
    if (value !== undefined && value !== '')
      params.set(key, String(value))
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

const accountPath = (accountId: string) =>
  `${ACCOUNTS_BASE}/${encodeURIComponent(accountId)}`

const challengePath = (challengeSessionId: string, suffix = '') =>
  `${CHALLENGE_BASE}/${encodeURIComponent(challengeSessionId)}${suffix}`

const taskPath = (taskId: string) =>
  `${TASKS_BASE}/${encodeURIComponent(taskId)}`

export const fetchSocialPublishAccounts = (platform?: SocialPublishPlatform) =>
  withErrorNormalization(
    get<{ data: SocialPublishAccount[] }>(
      `${ACCOUNTS_BASE}${buildQuery({ platform })}`,
    ),
  )

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
    del<{ result: 'success' }>(accountPath(accountId)),
  )

// ---------- P7: SMS challenge relay ----------

export const fetchSocialPublishChallenge = (challengeSessionId: string) =>
  withErrorNormalization(
    get<ChallengeSessionInfo>(challengePath(challengeSessionId)),
  )

export const triggerSocialPublishChallengeSms = (challengeSessionId: string) =>
  withErrorNormalization(
    post<ChallengeSessionInfo>(
      challengePath(challengeSessionId, '/trigger-sms'),
    ),
  )

export const submitSocialPublishChallengeCode = (
  challengeSessionId: string,
  code: string,
) =>
  withErrorNormalization(
    post<ChallengeSessionInfo>(
      challengePath(challengeSessionId, '/submit-code'),
      { body: { code } },
    ),
  )

export const abortSocialPublishChallenge = (challengeSessionId: string) =>
  withErrorNormalization(
    post<ChallengeSessionInfo>(challengePath(challengeSessionId, '/abort')),
  )

// ---------- P2: publish tasks ----------

export const createSocialPublishTask = (body: CreateTaskRequest) =>
  withErrorNormalization(post<CreateTaskResponse>(TASKS_BASE, { body }))

export const createSocialPublishTasksBatch = (body: BatchCreateTaskRequest) =>
  withErrorNormalization(
    post<BatchCreateTaskResponse>(`${TASKS_BASE}/batch`, { body }),
  )

export const fetchSocialPublishTask = (taskId: string) =>
  withErrorNormalization(get<TaskStatusResponse>(taskPath(taskId)))

export const listSocialPublishTasks = (filters?: {
  account_id?: string
  status?: SocialPublishTaskStatus
  limit?: number
}) =>
  withErrorNormalization(
    get<{ data: SocialPublishTask[] }>(
      `${TASKS_BASE}${buildQuery({
        account_id: filters?.account_id,
        status: filters?.status,
        limit: filters?.limit,
      })}`,
    ),
  )
