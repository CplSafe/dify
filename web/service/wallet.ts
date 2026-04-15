import { get, post } from '@/service/base'

const WALLET_BASE = '/workspaces/current/wallet'
const TOPUP_ORDERS_BASE = '/workspaces/current/topup/orders'

// Backend speaks fen (integer cents, Alipay's native unit); the UI speaks
// yuan. Keep the conversion pinned to the service layer so components
// never see fen — it's a wire-protocol detail, not a UI concern.
const yuanToFen = (yuan: number): number => Math.round(yuan * 100)
const fenToYuan = (fen: number): number => fen / 100

// Wire shapes are private: callers should use the yuan-denominated domain
// types below.
type TopupOrderWire = {
  order_id: string
  out_trade_no: string
  provider: string
  provider_trade_no: string | null
  tenant_id: string
  account_id: string
  amount: string
  amount_fen: number
  subject: string
  status: TopupOrderStatus
  qr_code: string | null
  pay_url: string | null
  paid_at: string | null
  expires_at: string | null
  created_at: string
}

type CreateTopupOrderWire = {
  order_id: string
  out_trade_no: string
  provider: string
  amount_fen: number
  qr_code: string | null
  pay_url: string | null
  expires_at: string
}

export type WalletBalance = {
  tenant: {
    tenant_id: string
    balance: string
    locked: string
    total_topup: string
    total: string
    currency: string
    updated_at: string
  }
  user: {
    account_id: string
    balance: string
    currency: string
    is_sufficient: boolean
    updated_at: string
  }
}

export type TopupOrderStatus
  = | 'pending'
    | 'paid'
    | 'closed'
    | 'expired'
    | 'failed'

type WithYuan<T extends { amount_fen: number }> = Omit<T, 'amount_fen'> & {
  amount_yuan: number
}

export type TopupOrder = WithYuan<TopupOrderWire>

export type CreateTopupOrderPayload = {
  amount_yuan: number
  subject?: string
}

export type CreateTopupOrderResponse = WithYuan<CreateTopupOrderWire>

const withYuan = <T extends { amount_fen: number }>(wire: T): WithYuan<T> => {
  const { amount_fen, ...rest } = wire
  return { ...rest, amount_yuan: fenToYuan(amount_fen) }
}

const orderPath = (outTradeNo: string, suffix = '') =>
  `${TOPUP_ORDERS_BASE}/${outTradeNo}${suffix}`

export const fetchWallet = () => get<WalletBalance>(WALLET_BASE)

export const createTopupOrder = (
  payload: CreateTopupOrderPayload,
): Promise<CreateTopupOrderResponse> =>
  post<CreateTopupOrderWire>(TOPUP_ORDERS_BASE, {
    body: {
      amount_fen: yuanToFen(payload.amount_yuan),
      subject: payload.subject,
    },
  }).then(withYuan)

export const fetchTopupOrder = (outTradeNo: string): Promise<TopupOrder> =>
  get<TopupOrderWire>(orderPath(outTradeNo)).then(withYuan)

export const closeTopupOrder = (outTradeNo: string): Promise<TopupOrder> =>
  post<TopupOrderWire>(orderPath(outTradeNo, '/close')).then(withYuan)

// ---------------------------------------------------------------------------
// List endpoints
// ---------------------------------------------------------------------------

export type TopupOrderListQuery = {
  limit?: number
  offset?: number
  status?: TopupOrderStatus
}

export type TopupOrderListResponse = {
  data: TopupOrder[]
  total: number
  limit: number
  offset: number
}

type TopupOrderListWire = {
  data: TopupOrderWire[]
  total: number
  limit: number
  offset: number
}

const buildQuery = (params: Record<string, string | number | undefined>) => {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '')
      qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

const toListResponse = (wire: TopupOrderListWire): TopupOrderListResponse => ({
  ...wire,
  data: wire.data.map(withYuan),
})

export const listTopupOrders = (
  query: TopupOrderListQuery = {},
): Promise<TopupOrderListResponse> =>
  get<TopupOrderListWire>(`${TOPUP_ORDERS_BASE}${buildQuery(query)}`).then(
    toListResponse,
  )

// ---------------------------------------------------------------------------
// Super-admin endpoints
// ---------------------------------------------------------------------------

export type AdminTopupOrderListQuery = TopupOrderListQuery & {
  tenant_id?: string
  account_id?: string
}

export const listAdminTopupOrders = (
  query: AdminTopupOrderListQuery = {},
): Promise<TopupOrderListResponse> =>
  get<TopupOrderListWire>(
    `/creator/admin/topup/orders${buildQuery(query)}`,
  ).then(toListResponse)

// ---------------------------------------------------------------------------
// Member allocation endpoints (tenant <-> member fund transfers)
// ---------------------------------------------------------------------------

// Backend speaks signed yuan as a decimal string — positive allocates tenant
// -> member, negative reclaims member -> tenant. We keep the wire contract
// verbatim so the console can render "+¥10" / "-¥5" without re-deriving sign.
export type AllocationRecord = {
  id: string
  tenant_id: string
  account_id: string
  operator_id: string
  amount: string
  description: string | null
  created_at: string
}

export type AllocateMemberPayload = {
  amount_yuan: number
  description?: string
}

export const allocateToMember = (
  memberId: string,
  payload: AllocateMemberPayload,
): Promise<AllocationRecord> =>
  post<AllocationRecord>(
    `/workspaces/current/members/${memberId}/allocations`,
    {
      body: {
        amount: payload.amount_yuan,
        description: payload.description,
      },
    },
  )

export type AllocationListQuery = {
  limit?: number
  offset?: number
}

export type AllocationListResponse = {
  data: AllocationRecord[]
  total: number
  limit: number
  offset: number
}

export const listAllocations = (
  query: AllocationListQuery = {},
): Promise<AllocationListResponse> =>
  get<AllocationListResponse>(
    `/workspaces/current/allocations${buildQuery(query)}`,
  )

// Member balance snapshot — owner-only. Lets the 成员管理 page show
// each member's current wallet before the owner decides how much to
// allocate or reclaim. Balance is a decimal string (yuan), matching the
// wallet payload contract.
export type MemberBalance = {
  account_id: string
  balance: string
  currency: string
}

export type MemberBalanceListResponse = {
  data: MemberBalance[]
}

export const listMemberBalances = (): Promise<MemberBalanceListResponse> =>
  get<MemberBalanceListResponse>('/workspaces/current/members/balances')
