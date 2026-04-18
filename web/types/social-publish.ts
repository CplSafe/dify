export type SocialPublishPlatform = 'douyin' | 'xhs' | 'ks'

export type SocialPublishAccountStatus
  = | 'pending_auth'
    | 'active'
    | 'expired'

export type SocialPublishAccount = {
  id: string
  platform: SocialPublishPlatform
  display_name: string | null
  avatar_url: string | null
  status: SocialPublishAccountStatus
  last_check_at: string | null
  created_at: string
}

export type AuthSessionStatus
  = | 'waiting'
    | 'scanned'
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
}

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
