// Account

export type SocialPublishPlatform = 'douyin' | 'xhs' | 'ks'

export type SocialPublishAccountStatus = 'pending_auth' | 'active' | 'expired'

export type SocialPublishAccount = {
  id: string
  platform: SocialPublishPlatform
  display_name: string | null
  avatar_url: string | null
  status: SocialPublishAccountStatus
  last_check_at: string | null
  created_at: string
}

// Auth (QR)

export type AuthSessionStatus
  = | 'waiting'
    | 'scanned'
    | 'awaiting_user' // P7: SMS challenge needs user input
    | 'success'
    | 'expired'
    | 'failed'

export type AuthStartResponse = {
  session_id: string
  qr_image_base64: string
  expires_in: number
}

export type AuthStatusResponse = {
  status: AuthSessionStatus
  account: SocialPublishAccount | null
  message: string | null
  /** When status === 'awaiting_user', the SMS-relay session id sau spawned. */
  challenge_session_id: string | null
}

// Auth (P7: SMS challenge, surfaced via /accounts/auth/challenge/{id})

export type ChallengeSessionStatus
  = | 'awaiting_user' // waiting for trigger SMS or submit code
    | 'user_submitted' // user submitted; sau worker hasn't picked up yet
    | 'completed' // sau worker consumed the action; flow continues
    | 'aborted' // user gave up or session timed out

export type ChallengeSessionInfo = {
  session_id: string
  platform: string
  kind: 'sms'
  status: ChallengeSessionStatus
  last_action_detail: string | null
  created_at: number
  updated_at: number
}

// Tasks

export type SocialPublishErrorCode
  = | 'feature_disabled'
    | 'platform_unsupported'
    | 'account_not_found'
    | 'tenant_mismatch'
    | 'account_expired'
    | 'session_expired'
    | 'sau_unreachable'
    | 'sau_api_error'
    | 'social_publish_error'
    | 'task_not_found'
    | 'task_invalid_payload'
    | 'task_already_in_flight'
    | 'work_not_found'
    | 'video_not_found'
    | 'video_too_large'
    | 'cookie_invalid'
    | 'upload_timeout'
    | 'upload_failed'
    | 'worker_crashed'

export type SocialPublishTaskStatus
  = | 'pending'
    | 'queued'
    | 'running'
    | 'success'
    | 'failed'

type TaskError = {
  error_code: SocialPublishErrorCode | string | null
  error_message: string | null
}

export type SocialPublishTask = TaskError & {
  id: string
  account_id: string
  work_id: string | null
  platform: SocialPublishPlatform
  status: SocialPublishTaskStatus
  result_url: string | null
  created_at: string
  updated_at: string
}

/**
 * Per-platform extras forwarded to the uploader. Keys outside the
 * per-platform allowlist are dropped server-side; `location` is capped
 * at 80 chars and silently omitted for platforms whose uploader has no
 * location field (currently ks).
 */
export type SocialPublishPlatformPayload = {
  location?: string
}

type TaskContent = {
  title: string
  tags?: string[]
  desc?: string
}

export type CreateTaskRequest = TaskContent & {
  account_id: string
  work_id: string
  platform_payload?: SocialPublishPlatformPayload
}

export type CreateTaskResponse = {
  task_id: string
  status: SocialPublishTaskStatus
}

export type BatchCreateTaskTarget = {
  account_id: string
  platform_payload?: SocialPublishPlatformPayload
}

export type BatchCreateTaskRequest = TaskContent & {
  work_id: string
  targets: BatchCreateTaskTarget[]
}

export type BatchCreateResultItem = TaskError & {
  account_id: string
  success: boolean
  task_id: string | null
}

export type BatchCreateTaskResponse = {
  results: BatchCreateResultItem[]
}

export type TaskStatusResponse = {
  task: SocialPublishTask
  result: TaskError & { url: string | null }
}
