import { type } from '@orpc/contract'
import { base } from '../base'

export type AgentPublicView = {
  name: string
  level: 'national' | 'province' | 'city' | null
  region_province: string | null
  region_city: string | null
}

export const agentBindPreviewContract = base
  .route({ method: 'GET', path: '/agent/bind/preview' })
  .input(type<{ query: { code: string } }>())
  .output(type<AgentPublicView>())

export const agentBindConfirmContract = base
  .route({ method: 'POST', path: '/agent/bind/confirm' })
  .input(type<{ body: { code: string } }>())
  .output(type<{ agent: AgentPublicView }>())

export const agentRebindRequestContract = base
  .route({ method: 'POST', path: '/agent/bind/rebind-request' })
  .input(type<{ body: { from_agent_id: string, to_agent_id: string } }>())
  .output(type<{ id: string, status: 'pending' | 'approved' | 'rejected' }>())
