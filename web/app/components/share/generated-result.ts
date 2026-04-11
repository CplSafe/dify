export type GeneratedResultPayload = {
  content: string
  success: boolean
  query?: string
  inputs?: Record<string, unknown>
  messageId?: string
  workflowRunId?: string
  conversationId?: string
}
