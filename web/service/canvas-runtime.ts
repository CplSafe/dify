import type {
  IOnCompleted,
  IOnData,
  IOnError,
  IOnMessageEnd,
  IOnNodeFinished,
  IOnNodeStarted,
  IOnWorkflowFinished,
  IOnWorkflowStarted,
  IOWorkflowPaused,
} from './base'
import { get, ssePost } from './base'

export type CanvasRuntimeChatBody = {
  query: string
  inputs?: Record<string, unknown>
  files?: unknown[]
  conversation_id?: string
}

export type CanvasRuntimeChatHandlers = {
  onData: IOnData
  onCompleted: IOnCompleted
  onError: IOnError
  onMessageEnd?: IOnMessageEnd
  onWorkflowStarted?: IOnWorkflowStarted
  onWorkflowFinished?: IOnWorkflowFinished
  onWorkflowPaused?: IOWorkflowPaused
  onNodeStarted?: IOnNodeStarted
  onNodeFinished?: IOnNodeFinished
  getAbortController?: (controller: AbortController) => void
}

export type CanvasRuntimeGraphResp = {
  nodes: Array<{ id: string, data?: { show_in_canvas_runtime?: boolean } }>
  edges: Array<{ source: string, target: string }>
}

// URL id is installed_app_id (not app_id); installed-apps covers any app in
// the user's workspace, while trial-apps would require a marketplace publish.
const path = (installedAppId: string, suffix: string) =>
  `installed-apps/${installedAppId}/${suffix}`

export const runChatflowOnCanvas = (
  installedAppId: string,
  body: CanvasRuntimeChatBody,
  handlers: CanvasRuntimeChatHandlers,
) =>
  ssePost(
    path(installedAppId, 'chat-messages'),
    { body: { ...body, response_mode: 'streaming' } },
    handlers,
  )

export const fetchCanvasAppParameters = (
  installedAppId: string,
): Promise<Record<string, unknown>> => get(path(installedAppId, 'parameters'))

export const fetchCanvasRuntimeGraph = (
  installedAppId: string,
): Promise<CanvasRuntimeGraphResp> =>
  get(path(installedAppId, 'runtime-graph'))
