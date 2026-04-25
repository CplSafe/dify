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
import { ssePost } from './base'

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

// Routes through the trial-app prefix to match the creator allow-list (_CREATOR_ALLOWED_PREFIXES).
export const runChatflowOnCanvas = (
  appId: string,
  body: CanvasRuntimeChatBody,
  handlers: CanvasRuntimeChatHandlers,
) =>
  ssePost(
    `trial-apps/${appId}/chat-messages`,
    { body: { ...body, response_mode: 'streaming' } },
    handlers,
  )
