'use client'

import type { ChatflowRerunKind } from '@/service/debug'
import { createContext, useContext } from 'react'

export type NodeRerunFlags = {
  allowEditInput: boolean
  allowEditOutput: boolean
}

export type RerunController = {
  appId: string
  messageId: string
  // Per-node permission flags read from the workflow draft (`node.data.allow_user_edit_*`).
  // Returns null when the node is not present on the canvas — those nodes
  // should be treated as "no rerun affordance".
  getNodeRerunFlags: (nodeId: string) => NodeRerunFlags | null
  onRerunFromNode: (nodeId: string, kind: ChatflowRerunKind) => void
}

// `null` means the surrounding chat surface does not support rerun
// (e.g. the public webapp, or a non-latest assistant message).
export const RerunContext = createContext<RerunController | null>(null)

export const useRerunController = (): RerunController | null => {
  return useContext(RerunContext)
}
