import { type } from "@orpc/contract";
import { base } from "../base";

export type AgentLevel = "national" | "province" | "city";
export type AgentStatus = "active" | "suspended";
export type RebindStatus = "pending" | "approved" | "rejected";
export type WithdrawalStatus = "pending" | "paid" | "rejected";
export type PayoutMethod = "alipay" | "wechat" | "bank";

export type Agent = {
  id: string;
  account_id: string;
  name: string;
  status: AgentStatus;
  rebate_rate: string | null;
  level: AgentLevel | null;
  region_province: string | null;
  region_city: string | null;
  contact_phone: string | null;
  notes: string | null;
  signed_at: string | null;
  expires_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type AgentCreateBody = {
  account_id: string;
  name: string;
  rebate_rate?: string | null;
  level?: AgentLevel | null;
  region_province?: string | null;
  region_city?: string | null;
  contact_phone?: string | null;
  notes?: string | null;
  signed_at?: string | null;
  expires_at?: string | null;
};

export type AgentPatchBody = Partial<Omit<AgentCreateBody, "account_id">>;

export type RebindRequest = {
  id: string;
  account_id: string;
  from_agent_id: string;
  to_agent_id: string;
  status: RebindStatus;
  reviewer_id: string | null;
  review_note: string | null;
  created_at: string | null;
  reviewed_at: string | null;
};

export type WithdrawalRequest = {
  id: string;
  agent_id: string;
  amount: string;
  payout_method: PayoutMethod;
  payout_payload: Record<string, string>;
  status: WithdrawalStatus;
  reviewer_id: string | null;
  review_note: string | null;
  created_at: string | null;
  reviewed_at: string | null;
};

export type RebateRecord = {
  id: string;
  inviter_account_id: string;
  agent_id: string;
  invitee_account_id: string;
  settlement_date: string;
  consumption_amount: string;
  rebate_amount: string;
  status: string;
  created_at: string | null;
};

export type ConsumptionRow = {
  agent_id: string;
  name: string;
  status: string;
  level: string | null;
  region_province: string | null;
  region_city: string | null;
  invitee_count: number;
  withdrawable: string;
  total_earned: string;
  total_withdrawn: string;
  last_30d_consumption: string;
};

type Page<T> = { data: T[]; page: number; limit: number; has_more: boolean };
type PageQuery<F = {}> = { query?: { page?: number; limit?: number } & F };
type AgentP = { params: { agent_id: string } };
type ReqP = { params: { request_id: string } };

const define = <I, O>(method: "GET" | "POST" | "PATCH", path: string) =>
  base.route({ method, path }).input(type<I>()).output(type<O>());

export const adminAgentCreateContract = define<
  { body: AgentCreateBody },
  Agent
>("POST", "/admin/agents");

export const adminAgentListContract = define<
  PageQuery<{ status?: AgentStatus }>,
  Page<Agent>
>("GET", "/admin/agents");

export const adminAgentDetailContract = define<AgentP, Agent>(
  "GET",
  "/admin/agents/{agent_id}",
);

export const adminAgentPatchContract = define<
  AgentP & { body: AgentPatchBody },
  Agent
>("PATCH", "/admin/agents/{agent_id}");

export const adminAgentSuspendContract = define<AgentP, Agent>(
  "POST",
  "/admin/agents/{agent_id}/suspend",
);

export const adminRebindListContract = define<
  PageQuery<{ status?: RebindStatus }>,
  Page<RebindRequest>
>("GET", "/admin/rebind-requests");

export const adminRebindApproveContract = define<
  ReqP & { body: { note?: string } },
  RebindRequest
>("POST", "/admin/rebind-requests/{request_id}/approve");

export const adminRebindRejectContract = define<
  ReqP & { body: { note: string } },
  RebindRequest
>("POST", "/admin/rebind-requests/{request_id}/reject");

export const adminWithdrawalListContract = define<
  PageQuery<{ status?: WithdrawalStatus }>,
  Page<WithdrawalRequest>
>("GET", "/admin/withdrawals");

export const adminWithdrawalPayContract = define<
  ReqP & { body: { transaction_id: string } },
  WithdrawalRequest
>("POST", "/admin/withdrawals/{request_id}/pay");

export const adminWithdrawalRejectContract = define<
  ReqP & { body: { note: string } },
  WithdrawalRequest
>("POST", "/admin/withdrawals/{request_id}/reject");

export const adminRebateRecordsContract = define<
  PageQuery<{ agent_id?: string; from?: string; to?: string }>,
  Page<RebateRecord>
>("GET", "/admin/rebate-records");

export const adminAgentConsumptionContract = define<
  void,
  { data: ConsumptionRow[] }
>("GET", "/admin/agent-consumption");
