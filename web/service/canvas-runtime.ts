import type {
  IOHumanInputRequired,
  IOnCompleted,
  IOnData,
  IOnError,
  IOnHumanInputFormFilled,
  IOnHumanInputFormTimeout,
  IOnMessageEnd,
  IOnNodeFinished,
  IOnNodeStarted,
  IOnWorkflowFinished,
  IOnWorkflowStarted,
  IOWorkflowPaused,
} from './base'
import type { ChatflowRerunKind } from './debug'
import { del, get, post, put, sseGet, ssePost } from './base'

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
  // Human-input lifecycle: required → filled / timeout. Canvas runtime
  // surfaces these via a slide-in drawer keyed by node_id.
  onHumanInputRequired?: IOHumanInputRequired
  onHumanInputFormFilled?: IOnHumanInputFormFilled
  onHumanInputFormTimeout?: IOnHumanInputFormTimeout
  getAbortController?: (controller: AbortController) => void
}

export type CanvasRuntimeGraphResp = {
  nodes: Array<{
    id: string
    data?: {
      show_in_canvas_runtime?: boolean
      // CR10: per-node toggles set in the workflow editor. Used by the
      // runtime card to decide whether to render the 重跑 trigger.
      allow_user_edit_input?: boolean
      allow_user_edit_output?: boolean
    }
  }>
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

// CR10: rerun + override CRUD scoped to installed-apps so canvas-runtime
// users (creators, not console admins) can edit a completed node and rerun
// from there. Mirror of the admin endpoints in `service/debug.ts`.
type RerunArgs = {
  installedAppId: string
  messageId: string
  nodeId: string
}

type RerunArgsWithKind = RerunArgs & { kind: ChatflowRerunKind }

const messagePath = (
  { installedAppId, messageId }: RerunArgs,
  suffix: string,
) => path(installedAppId, `messages/${messageId}/${suffix}`)

export const prepareCanvasRerun = (args: RerunArgsWithKind) =>
  post(messagePath(args, 'rerun-from'), {
    body: { node_id: args.nodeId, kind: args.kind },
  })

export const dispatchCanvasRerun = (args: RerunArgsWithKind) =>
  post(messagePath(args, 'rerun-from/dispatch'), {
    body: { node_id: args.nodeId, kind: args.kind },
  })

export const upsertCanvasRerunOverride = (
  args: RerunArgsWithKind & { data: Record<string, unknown> },
) =>
  put(messagePath(args, 'rerun-overrides'), {
    body: { node_id: args.nodeId, kind: args.kind, data: args.data },
  })

export const deleteCanvasRerunOverride = (
  args: RerunArgs & { kind?: ChatflowRerunKind },
) => {
  const search = args.kind ? `?kind=${args.kind}` : ''
  return del(
    messagePath(
      args,
      `rerun-overrides/${encodeURIComponent(args.nodeId)}${search}`,
    ),
  )
}

// CR10 review fix: creator-side "继续" was pointing at the admin
// `/apps/.../resume-from` route, which requires console-app permissions
// the canvas-runtime user doesn't have. Use the installed-apps mirror
// instead; default kind='output' matches the user-facing semantics
// (paused node's output is fine — advance to the next node).
export const resumeCanvasFromNode = (
  args: RerunArgs & { kind?: ChatflowRerunKind },
) =>
  post(messagePath(args, `resume-from/${encodeURIComponent(args.nodeId)}`), {
    body: args.kind ? { kind: args.kind } : {},
  })

/**
 * Re-subscribe to a workflow_run's SSE topic after the original chatflow
 * stream ended (paused on human-input, then resumed). Without this the
 * canvas would never see the post-pause node_started/node_finished
 * events because the original `ssePost` connection has already closed.
 *
 * Reuses the same handler shape as runChatflowOnCanvas so the page can
 * pass the same dispatcher object — every event type the engine emits
 * post-resume is identical to a fresh-start run.
 */
export const subscribeToCanvasRunEvents = (
  workflowRunId: string,
  handlers: CanvasRuntimeChatHandlers,
) =>
  sseGet(
    `/workflow/${workflowRunId}/events?include_state_snapshot=true`,
    {},
    handlers,
  )
