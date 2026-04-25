'use client'

import { create } from 'zustand'

export type NodeRuntimeStatus
  = | 'pending'
    | 'running'
    | 'succeeded'
    | 'failed'
    | 'paused'

export type RuntimeNode = {
  // Stable canvas-side id (matches the workflow draft node id).
  id: string
  type: string // BlockEnum string
  title: string
  position: { x: number, y: number }
  status: NodeRuntimeStatus
  inputs?: Record<string, unknown>
  outputs?: Record<string, unknown>
  error?: string
}

export type RuntimeEdge = {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
}

export type SSEEvent
  = | {
    type: 'workflow_started'
    workflowRunId: string
  }
  | {
    type: 'node_started'
    nodeId: string
    nodeType: string
    title: string
    inputs?: Record<string, unknown>
    predecessorNodeId?: string
  }
  | {
    type: 'node_finished'
    nodeId: string
    outputs?: Record<string, unknown>
    status: 'succeeded' | 'failed'
    error?: string
  }
  | {
    type: 'workflow_paused'
    pausedNodeIds: string[]
    // Encoded reason from CR1: "user_edit:<node_id>:input,output" or
    // a HumanInputRequired payload from the existing infrastructure.
    reasons: string[]
  }
  | {
    type: 'workflow_finished'
    workflowRunId: string
  }

type RuntimeState = {
  workflowRunId: string | null
  nodes: Record<string, RuntimeNode>
  edges: Record<string, RuntimeEdge>
  // Insertion order so the canvas reveals nodes left-to-right rather
  // than ReactFlow's auto-layout deciding alphabetically.
  visibleOrder: string[]
  // Ids of nodes the user can interact with right now (paused for edit
  // OR human-input form open). Drives CR6's inline buttons.
  pausedNodeIds: string[]
  // For diagnostic only — exposed in the toolbar.
  lastEventAt: number | null

  applyEvent: (event: SSEEvent) => void
  reset: () => void
}

const _initialState = {
  workflowRunId: null,
  nodes: {} as Record<string, RuntimeNode>,
  edges: {} as Record<string, RuntimeEdge>,
  visibleOrder: [] as string[],
  pausedNodeIds: [] as string[],
  lastEventAt: null as number | null,
}

// Lay nodes out left-to-right by their reveal order. The real workflow
// editor uses dagre — for the runtime a simple offset is enough until
// users ask for branching layouts.
const _nodeOffset = 240
const _nodeY = 0

const _placeNode = (index: number) => ({
  x: index * _nodeOffset,
  y: _nodeY,
})

export const useRuntimeStore = create<RuntimeState>((set, get) => ({
  ..._initialState,

  applyEvent: (event) => {
    const now = Date.now()
    if (event.type === 'workflow_started') {
      set({
        ..._initialState,
        workflowRunId: event.workflowRunId,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'node_started') {
      const { nodes, edges, visibleOrder } = get()
      const existing = nodes[event.nodeId]
      const nextOrder = existing ? visibleOrder : [...visibleOrder, event.nodeId]
      const nextNodes = {
        ...nodes,
        [event.nodeId]: {
          id: event.nodeId,
          type: event.nodeType,
          title: event.title,
          position: existing?.position ?? _placeNode(nextOrder.length - 1),
          status: 'running' as NodeRuntimeStatus,
          inputs: event.inputs,
          // Carry forward outputs if the engine restarts a node we've
          // seen before (e.g. retry).
          outputs: existing?.outputs,
        },
      }
      const nextEdges = { ...edges }
      if (event.predecessorNodeId && nodes[event.predecessorNodeId]) {
        const edgeId = `${event.predecessorNodeId}->${event.nodeId}`
        if (!nextEdges[edgeId]) {
          nextEdges[edgeId] = {
            id: edgeId,
            source: event.predecessorNodeId,
            target: event.nodeId,
          }
        }
      }
      set({
        nodes: nextNodes,
        edges: nextEdges,
        visibleOrder: nextOrder,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'node_finished') {
      const { nodes } = get()
      const existing = nodes[event.nodeId]
      if (!existing)
        return
      set({
        nodes: {
          ...nodes,
          [event.nodeId]: {
            ...existing,
            status: event.status,
            outputs: event.outputs,
            error: event.error,
          },
        },
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'workflow_paused') {
      const { nodes } = get()
      const paused = event.pausedNodeIds.filter(id => nodes[id])
      const nextNodes = { ...nodes }
      for (const id of paused) {
        nextNodes[id] = { ...nextNodes[id], status: 'paused' }
      }
      set({
        nodes: nextNodes,
        pausedNodeIds: paused,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'workflow_finished') {
      // Clear pause markers — finishing implies all pauses resolved.
      set({ pausedNodeIds: [], lastEventAt: now })
    }
  },

  reset: () => set({ ..._initialState }),
}))
