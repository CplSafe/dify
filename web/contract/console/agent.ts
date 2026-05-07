import { type } from '@orpc/contract'
import { base } from '../base'

// ---------------------------------------------------------------------------
// Shared response types
// ---------------------------------------------------------------------------

export type WalletSummary = {
  withdrawable: string
  total_earned: string
  total_withdrawn: string
  pending: string
}

export type TrendPoint = {
  date: string
  consumption: string
}

export type DashboardResponse = {
  wallet: WalletSummary
  trend: TrendPoint[]
}

export type Invitee = {
  invitee_account_id: string
  bound_at: string | null
  month_consumption: string
  total_rebate: string
}

export type InvitationCode = {
  invite_code: string
  created_at: string | null
}

export type PayoutMethod = 'alipay' | 'wechat' | 'bank'

export type AlipayPayload = { account: string, name: string }
export type WechatPayload = { wechat_id: string, name: string }
export type BankPayload = { bank: string, account: string, name: string }
export type PayoutPayload = AlipayPayload | WechatPayload | BankPayload

export type WithdrawalRequest = {
  id: string
  amount: string
  payout_method: PayoutMethod
  payout_payload: PayoutPayload | Record<string, string>
  status: 'pending' | 'paid' | 'rejected'
  review_note: string | null
  created_at: string | null
  reviewed_at: string | null
}

type Paged<T> = {
  data: T[]
  page: number
  limit: number
  has_more: boolean
}

// ---------------------------------------------------------------------------
// Contracts
// ---------------------------------------------------------------------------

export const agentDashboardContract = base
  .route({ method: 'GET', path: '/agent/dashboard' })
  .input(type<{ query?: { days?: number } }>())
  .output(type<DashboardResponse>())

export const agentInviteesContract = base
  .route({ method: 'GET', path: '/agent/invitees' })
  .input(type<unknown>())
  .output(type<{ data: Invitee[] }>())

export const agentInvitationsListContract = base
  .route({ method: 'GET', path: '/agent/invitations' })
  .input(type<unknown>())
  .output(type<{ data: InvitationCode[] }>())

export const agentInvitationsCreateContract = base
  .route({ method: 'POST', path: '/agent/invitations' })
  .input(type<unknown>())
  .output(type<{ invite_code: string }>())

export const agentWithdrawalsListContract = base
  .route({ method: 'GET', path: '/agent/withdrawals' })
  .input(type<{ query?: { page?: number, limit?: number } }>())
  .output(type<Paged<WithdrawalRequest>>())

export const agentWithdrawalsCreateContract = base
  .route({ method: 'POST', path: '/agent/withdrawals' })
  .input(type<{
    body: {
      amount: string
      payout_method: PayoutMethod
      payout_payload: PayoutPayload | Record<string, string>
    }
  }>())
  .output(type<WithdrawalRequest>())
