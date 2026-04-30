import { type } from '@orpc/contract'
import { base } from '../base'

export type WalletSummary = {
  withdrawable: string
  total_earned: string
  total_withdrawn: string
  pending: string
}

export type TrendPoint = {
  date: string // YYYY-MM-DD
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

type PayoutPayloadInput = PayoutPayload | Record<string, string>

export type WithdrawalRequest = {
  id: string
  amount: string
  payout_method: PayoutMethod
  payout_payload: PayoutPayloadInput
  status: 'pending' | 'paid' | 'rejected'
  review_note: string | null
  created_at: string | null
  reviewed_at: string | null
}

const define = <I, O>(method: 'GET' | 'POST', path: string) =>
  base.route({ method, path }).input(type<I>()).output(type<O>())

export const agentDashboardContract = define<
  { query?: { days?: number } },
  DashboardResponse
>('GET', '/agent/dashboard')

export const agentInviteesContract = define<
  unknown,
  { data: Invitee[] }
>('GET', '/agent/invitees')

export const agentInvitationsListContract = define<
  unknown,
  { data: InvitationCode[] }
>('GET', '/agent/invitations')

export const agentInvitationsCreateContract = define<
  unknown,
  { invite_code: string }
>('POST', '/agent/invitations')

export const agentWithdrawalsListContract = define<
  { query?: { page?: number, limit?: number } },
  {
    data: WithdrawalRequest[]
    page: number
    limit: number
    has_more: boolean
  }
>('GET', '/agent/withdrawals')

export const agentWithdrawalsCreateContract = define<
  {
    body: {
      amount: string
      payout_method: PayoutMethod
      payout_payload: PayoutPayloadInput
    }
  },
  WithdrawalRequest
>('POST', '/agent/withdrawals')
