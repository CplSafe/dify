import type {
  IOnCompleted,
  IOnData,
  IOnError,
  IOnMessageReplace,
} from './base'
import type { ChatPromptConfig, CompletionPromptConfig } from '@/models/debug'
import type { AppModeEnum, ModelModeType } from '@/types/app'
import { del, get, post, put, ssePost } from './base'

type BasicAppFirstRes = {
  prompt: string
  variables: string[]
  opening_statement: string
  error?: string
}

export type GenRes = {
  modified: string
  message?: string // tip for human
  variables?: string[] // only for basic app first time rule
  opening_statement?: string // only for basic app first time rule
  error?: string
}

export const stopChatMessageResponding = async (
  appId: string,
  taskId: string,
) => {
  return post(`apps/${appId}/chat-messages/${taskId}/stop`)
}

export const sendCompletionMessage = async (
  appId: string,
  body: Record<string, any>,
  {
    onData,
    onCompleted,
    onError,
    onMessageReplace,
  }: {
    onData: IOnData
    onCompleted: IOnCompleted
    onError: IOnError
    onMessageReplace: IOnMessageReplace
  },
) => {
  return ssePost(
    `apps/${appId}/completion-messages`,
    {
      body: {
        ...body,
        response_mode: 'streaming',
      },
    },
    { onData, onCompleted, onError, onMessageReplace },
  )
}

export const fetchSuggestedQuestions = (
  appId: string,
  messageId: string,
  getAbortController?: any,
) => {
  return get(
    `apps/${appId}/chat-messages/${messageId}/suggested-questions`,
    {},
    {
      getAbortController,
    },
  )
}

export const fetchConversationMessages = (
  appId: string,
  conversation_id: string,
  getAbortController?: any,
) => {
  return get(
    `apps/${appId}/chat-messages`,
    {
      params: {
        conversation_id,
      },
    },
    {
      getAbortController,
    },
  )
}

export const generateBasicAppFirstTimeRule = (body: Record<string, any>) => {
  return post<BasicAppFirstRes>('/rule-generate', {
    body,
  })
}

export const generateRule = (body: Record<string, any>) => {
  return post<GenRes>('/instruction-generate', {
    body,
  })
}

export const fetchPromptTemplate = ({
  appMode,
  mode,
  modelName,
  hasSetDataSet,
}: {
  appMode: AppModeEnum
  mode: ModelModeType
  modelName: string
  hasSetDataSet: boolean
}) => {
  return get<
    Promise<{
      chat_prompt_config: ChatPromptConfig
      completion_prompt_config: CompletionPromptConfig
      stop: []
    }>
  >('/app/prompt-templates', {
    params: {
      app_mode: appMode,
      model_mode: mode,
      model_name: modelName,
      has_context: hasSetDataSet,
    },
  })
}

export const fetchTextGenerationMessage = ({
  appId,
  messageId,
}: {
  appId: string
  messageId: string
}) => {
  return get<Promise<any>>(`/apps/${appId}/messages/${messageId}`)
}

// Chatflow node-level rerun (M1 prepare endpoint).
// Returns the rerun plan; the actual streaming dispatch lands in M7.
export type ChatflowRerunKind = 'input' | 'output'

export type ChatflowRerunPlan = {
  source_message_id: string
  source_run_id: string
  workflow_id: string
  rewind_node_id: string
  rewind_kind: ChatflowRerunKind
  start_node_id: string
  ancestor_node_ids: string[]
  ancestor_output_keys: Record<string, string[]>
  overrides_applied: Record<string, ChatflowRerunKind>
  is_busy: boolean
}

export const prepareChatflowRerun = ({
  appId,
  messageId,
  nodeId,
  kind,
}: {
  appId: string
  messageId: string
  nodeId: string
  kind: ChatflowRerunKind
}) => {
  return post<ChatflowRerunPlan>(
    `/apps/${appId}/messages/${messageId}/rerun-from`,
    {
      body: { node_id: nodeId, kind },
    },
  )
}

// CR1 dispatch endpoint. Resumes the paused chatflow run via the
// celery worker; returns immediately once the resume is enqueued.
export type ChatflowRerunDispatchResult = {
  status: 'started' | 'resumed'
  workflow_run_id: string
}

export const dispatchChatflowRerun = ({
  appId,
  messageId,
  nodeId,
  kind,
}: {
  appId: string
  messageId: string
  nodeId: string
  kind: ChatflowRerunKind
}) => {
  return post<ChatflowRerunDispatchResult>(
    `/apps/${appId}/messages/${messageId}/rerun-from/dispatch`,
    {
      body: { node_id: nodeId, kind },
    },
  )
}

// CR1 "继续" button: resume from a paused node without saving any new
// override. Same celery resume path as dispatch — the user just decided
// the rewind node's input/output is fine as-is.
export const resumeChatflowFromNode = ({
  appId,
  messageId,
  nodeId,
  kind,
}: {
  appId: string
  messageId: string
  nodeId: string
  kind?: ChatflowRerunKind
}) => {
  return post<ChatflowRerunDispatchResult>(
    `/apps/${appId}/messages/${messageId}/resume-from/${encodeURIComponent(nodeId)}`,
    {
      body: kind ? { kind } : {},
    },
  )
}

export type ChatflowRerunOverride = {
  id: string
  message_id: string
  workflow_run_id: string
  node_id: string
  kind: ChatflowRerunKind
  data: Record<string, unknown>
  created_by: string
  created_at: string | null
}

export const upsertChatflowRerunOverride = ({
  appId,
  messageId,
  nodeId,
  kind,
  data,
}: {
  appId: string
  messageId: string
  nodeId: string
  kind: ChatflowRerunKind
  data: Record<string, unknown>
}) => {
  return put<ChatflowRerunOverride>(
    `/apps/${appId}/messages/${messageId}/rerun-overrides`,
    {
      body: { node_id: nodeId, kind, data },
    },
  )
}

export const deleteChatflowRerunOverride = ({
  appId,
  messageId,
  nodeId,
  kind,
}: {
  appId: string
  messageId: string
  nodeId: string
  kind?: ChatflowRerunKind
}) => {
  const search = kind ? `?kind=${kind}` : ''
  return del<{ deleted: number }>(
    `/apps/${appId}/messages/${messageId}/rerun-overrides/${encodeURIComponent(nodeId)}${search}`,
  )
}
