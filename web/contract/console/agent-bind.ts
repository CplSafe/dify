import { type } from '@orpc/contract'
import { base } from '../base'

export type AgentLevel = 'national' | 'province' | 'city'
export type RebindStatus = 'pending' | 'approved' | 'rejected'

export type AgentPublicView = {
  name: string
  level: AgentLevel | null
  region_province: string | null
  region_city: string | null
}

const define = <I, O>(method: 'GET' | 'POST', path: string) =>
  base.route({ method, path }).input(type<I>()).output(type<O>())

export const agentBindPreviewContract = define<
  { query: { code: string } },
  AgentPublicView
>('GET', '/agent/bind/preview')

export const agentBindConfirmContract = define<
  { body: { code: string } },
  { agent: AgentPublicView }
>('POST', '/agent/bind/confirm')

export const agentRebindRequestContract = define<
  { body: { from_agent_id: string, to_agent_id: string } },
  { id: string, status: RebindStatus }
>('POST', '/agent/bind/rebind-request')
