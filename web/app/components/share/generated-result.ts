export type GeneratedResultPayload = {
  content: string
  success: boolean
  query?: string
  inputs?: Record<string, unknown>
  messageId?: string
  workflowRunId?: string
  conversationId?: string
  /** True when the workflow paused for human input at completion time */
  hasHumanInput?: boolean
}
