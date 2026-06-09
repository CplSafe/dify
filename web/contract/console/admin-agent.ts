import { type } from '@orpc/contract'
import { base } from '../base'

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type Agent = {
  id: string
  account_id: string
  name: string
  status: 'active' | 'suspended'
  rebate_rate: string | null
  level: 'national' | 'province' | 'city' | null
  region_province: string | null
  region_city: string | null
  contact_phone: string | null
  notes: string | null
  signed_at: string | null
  expires_at: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export type AgentCreateBody = {
  account_id: string
  name: string
  rebate_rate?: string | null
  level?: 'national' | 'province' | 'city' | null
  region_province?: string | null
  region_city?: string | null
  contact_phone?: string | null
  notes?: string | null
  signed_at?: string | null
  expires_at?: string | null
}

export type AgentPatchBody = Partial<Omit<AgentCreateBody, 'account_id'>>

export type RebindRequest = {
  id: string
  account_id: string
  from_agent_id: string
  to_agent_id: string
  status: 'pending' | 'approved' | 'rejected'
  reviewer_id: string | null
  review_note: string | null
  created_at: string | null
  reviewed_at: string | null
}

export type WithdrawalRequest = {
  id: string
  agent_id: string
  amount: string
  payout_method: 'alipay' | 'wechat' | 'bank'
  payout_payload: Record<string, string>
  status: 'pending' | 'paid' | 'rejected'
  reviewer_id: string | null
  review_note: string | null
  created_at: string | null
  reviewed_at: string | null
}

export type RebateRecord = {
  id: string
  inviter_account_id: string
  agent_id: string
  invitee_account_id: string
  settlement_date: string
  consumption_amount: string
  rebate_amount: string
  status: string
  created_at: string | null
}

export type ConsumptionRow = {
  agent_id: string
  name: string
  status: string
  level: string | null
  region_province: string | null
  region_city: string | null
  invitee_count: number
  withdrawable: string
  total_earned: string
  total_withdrawn: string
  last_30d_consumption: string
}

type Page<T> = {
  data: T[]
  page: number
  limit: number
  has_more: boolean
}

// ---------------------------------------------------------------------------
// Agent CRUD
// ---------------------------------------------------------------------------

export const adminAgentCreateContract = base
  .route({ method: 'POST', path: '/admin/agents' })
  .input(type<{ body: AgentCreateBody }>())
  .output(type<Agent>())

export const adminAgentListContract = base
  .route({ method: 'GET', path: '/admin/agents' })
  .input(type<{
    query?: {
      page?: number
      limit?: number
      status?: 'active' | 'suspended'
    }
  }>())
  .output(type<Page<Agent>>())

export const adminAgentDetailContract = base
  .route({ method: 'GET', path: '/admin/agents/{agent_id}' })
  .input(type<{ params: { agent_id: string } }>())
  .output(type<Agent>())

export const adminAgentPatchContract = base
  .route({ method: 'PATCH', path: '/admin/agents/{agent_id}' })
  .input(type<{ params: { agent_id: string }, body: AgentPatchBody }>())
  .output(type<Agent>())

export const adminAgentSuspendContract = base
  .route({ method: 'POST', path: '/admin/agents/{agent_id}/suspend' })
  .input(type<{ params: { agent_id: string } }>())
  .output(type<Agent>())

// ---------------------------------------------------------------------------
// Rebind review
// ---------------------------------------------------------------------------

export const adminRebindListContract = base
  .route({ method: 'GET', path: '/admin/rebind-requests' })
  .input(type<{
    query?: {
      page?: number
      limit?: number
      status?: 'pending' | 'approved' | 'rejected'
    }
  }>())
  .output(type<Page<RebindRequest>>())

export const adminRebindApproveContract = base
  .route({ method: 'POST', path: '/admin/rebind-requests/{request_id}/approve' })
  .input(type<{ params: { request_id: string }, body: { note?: string } }>())
  .output(type<RebindRequest>())

export const adminRebindRejectContract = base
  .route({ method: 'POST', path: '/admin/rebind-requests/{request_id}/reject' })
  .input(type<{ params: { request_id: string }, body: { note?: string } }>())
  .output(type<RebindRequest>())

// ---------------------------------------------------------------------------
// Withdrawal review
// ---------------------------------------------------------------------------

export const adminWithdrawalListContract = base
  .route({ method: 'GET', path: '/admin/withdrawals' })
  .input(type<{
    query?: {
      page?: number
      limit?: number
      status?: 'pending' | 'paid' | 'rejected'
    }
  }>())
  .output(type<Page<WithdrawalRequest>>())

export const adminWithdrawalPayContract = base
  .route({ method: 'POST', path: '/admin/withdrawals/{request_id}/pay' })
  .input(type<{ params: { request_id: string }, body: { transaction_id: string } }>())
  .output(type<WithdrawalRequest>())

export const adminWithdrawalRejectContract = base
  .route({ method: 'POST', path: '/admin/withdrawals/{request_id}/reject' })
  .input(type<{ params: { request_id: string }, body: { note: string } }>())
  .output(type<WithdrawalRequest>())

// ---------------------------------------------------------------------------
// Overviews
// ---------------------------------------------------------------------------

export const adminRebateRecordsContract = base
  .route({ method: 'GET', path: '/admin/rebate-records' })
  .input(type<{
    query?: {
      page?: number
      limit?: number
      agent_id?: string
      from?: string
      to?: string
    }
  }>())
  .output(type<Page<RebateRecord>>())

export const adminAgentConsumptionContract = base
  .route({ method: 'GET', path: '/admin/agent-consumption' })
  .input(type<unknown>())
  .output(type<{ data: ConsumptionRow[] }>())
