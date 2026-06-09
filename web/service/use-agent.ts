import type { PayoutMethod, PayoutPayload } from '@/contract/console/agent'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consoleClient, consoleQuery } from '@/service/client'

const { agent } = consoleQuery
const { agent: api } = consoleClient

export type CreateWithdrawalParams = {
  amount: string
  payout_method: PayoutMethod
  payout_payload: PayoutPayload | Record<string, string>
}

export type RebindRequestParams = {
  from_agent_id: string
  to_agent_id: string
}

export const useAgentDashboard = (days = 7) => {
  const query = { days }
  return useQuery({
    queryKey: agent.dashboard.queryKey({ input: { query } }),
    queryFn: () => api.dashboard({ query }),
  })
}

export const useAgentInvitees = () =>
  useQuery({
    queryKey: agent.invitees.queryKey({ input: {} }),
    queryFn: () => api.invitees({}),
  })

export const useAgentInvitations = () =>
  useQuery({
    queryKey: agent.invitationsList.queryKey({ input: {} }),
    queryFn: () => api.invitationsList({}),
  })

export const useGenerateInvitation = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: agent.invitationsCreate.mutationKey(),
    mutationFn: () => api.invitationsCreate({}),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: agent.invitationsList.queryKey({ input: {} }),
      })
    },
  })
}

export const useWithdrawalHistory = (page = 1, limit = 20) => {
  const query = { page, limit }
  return useQuery({
    queryKey: agent.withdrawalsList.queryKey({ input: { query } }),
    queryFn: () => api.withdrawalsList({ query }),
  })
}

export const useCreateWithdrawal = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: agent.withdrawalsCreate.mutationKey(),
    mutationFn: (params: CreateWithdrawalParams) =>
      api.withdrawalsCreate({ body: params }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: agent.withdrawalsList.queryKey({
          input: { query: { page: 1, limit: 20 } },
        }),
      })
      queryClient.invalidateQueries({
        queryKey: agent.dashboard.queryKey({ input: { query: { days: 7 } } }),
      })
    },
  })
}

export const useAgentPreview = (code: string | null) => {
  const query = { code: code ?? '' }
  return useQuery({
    queryKey: agent.bindPreview.queryKey({ input: { query } }),
    queryFn: () => api.bindPreview({ query }),
    enabled: !!code,
    retry: false,
  })
}

export const useConfirmBind = () =>
  useMutation({
    mutationKey: agent.bindConfirm.mutationKey(),
    mutationFn: (code: string) => api.bindConfirm({ body: { code } }),
  })

export const useRebindRequest = () =>
  useMutation({
    mutationKey: agent.rebindRequest.mutationKey(),
    mutationFn: (params: RebindRequestParams) =>
      api.rebindRequest({ body: params }),
  })
