import type {
  AgentCreateBody,
  WithdrawalRequest,
} from '@/contract/console/admin-agent'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consoleClient, consoleQuery } from '@/service/client'

const { adminAgent } = consoleQuery
const { adminAgent: api } = consoleClient

export const useAdminAgents = (
  query: { page: number, limit: number, status?: 'active' | 'suspended' },
) =>
  useQuery({
    queryKey: adminAgent.list.queryKey({ input: { query } }),
    queryFn: () => api.list({ query }),
  })

export const useAdminAgentConsumption = () =>
  useQuery({
    queryKey: adminAgent.consumption.queryKey({ input: undefined }),
    queryFn: () => api.consumption(undefined),
  })

export const useAdminRebateRecords = (
  query: { page: number, limit: number, agent_id?: string },
) =>
  useQuery({
    queryKey: adminAgent.rebateRecords.queryKey({ input: { query } }),
    queryFn: () => api.rebateRecords({ query }),
  })

export const useAdminRebindRequests = (
  query: { page: number, limit: number, status?: 'pending' | 'approved' | 'rejected' },
) =>
  useQuery({
    queryKey: adminAgent.rebindList.queryKey({ input: { query } }),
    queryFn: () => api.rebindList({ query }),
  })

export const useAdminWithdrawalRequests = (
  query: { page: number, limit: number, status?: 'pending' | 'paid' | 'rejected' },
) =>
  useQuery({
    queryKey: adminAgent.withdrawalList.queryKey({ input: { query } }),
    queryFn: () => api.withdrawalList({ query }),
  })

export const useCreateAdminAgent = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: adminAgent.create.mutationKey(),
    mutationFn: (body: AgentCreateBody) => api.create({ body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminAgent.list.key() })
      queryClient.invalidateQueries({ queryKey: adminAgent.consumption.key() })
    },
  })
}

export const useSuspendAdminAgent = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: adminAgent.suspend.mutationKey(),
    mutationFn: (agentId: string) =>
      api.suspend({ params: { agent_id: agentId } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminAgent.list.key() })
      queryClient.invalidateQueries({ queryKey: adminAgent.consumption.key() })
    },
  })
}

export const useReviewRebindRequest = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (
      input: { requestId: string, action: 'approve' | 'reject', note?: string },
    ) => {
      const body = { note: input.note }
      if (input.action === 'approve')
        return api.rebindApprove({ params: { request_id: input.requestId }, body })
      return api.rebindReject({ params: { request_id: input.requestId }, body })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminAgent.rebindList.key() })
    },
  })
}

export const useReviewWithdrawalRequest = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (
      input:
        | { request: WithdrawalRequest, action: 'pay', transactionId: string }
        | { request: WithdrawalRequest, action: 'reject', note: string },
    ) => {
      if (input.action === 'pay') {
        return api.withdrawalPay({
          params: { request_id: input.request.id },
          body: { transaction_id: input.transactionId },
        })
      }
      return api.withdrawalReject({
        params: { request_id: input.request.id },
        body: { note: input.note },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminAgent.withdrawalList.key() })
      queryClient.invalidateQueries({ queryKey: adminAgent.consumption.key() })
    },
  })
}
