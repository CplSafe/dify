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
  | {
    // Plain assistant text — chatflow sends these as `event: message`
    // chunks. Used for both LLM answers AND middleware bailouts (e.g.
    // a balance-check returning "余额不足，请充值"), so the canvas needs
    // to surface it even when no workflow node ever runs.
    type: 'message'
    text: string
    // `append` (default) concatenates onto the running answer.
    // `replace` swaps the buffer (for message_replace events).
    mode?: 'append' | 'replace'
  }
  | {
    type: 'message_end'
  }

// CR1 encodes pause reason as `user_edit:<node_id>:<kinds>` where
// kinds is a comma-joined list of "input" / "output". CR6 parses it
// to decide which buttons to show on the inline pause portal.
export type PausedNodeKinds = {
  allowInput: boolean
  allowOutput: boolean
  // 'human_input' fires the existing form flow; 'user_edit' fires the
  // M6 RerunOverrideModal.
  source: 'user_edit' | 'human_input'
}

// CR9: minimal projection of the chatflow draft graph. Only what the
// runtime store needs to decide visibility + pass-through edges. Page
// fetches it (via /apps/<id>/workflows/draft or workflow_run.graph)
// and hands it off via setGraphDict before the user starts a run.
export type RuntimeGraphDict = {
  nodes: Array<{
    id: string
    data?: { show_in_canvas_runtime?: boolean }
  }>
  edges: Array<{ source: string, target: string }>
}

type RuntimeState = {
  workflowRunId: string | null
  // Chatflow message id that backs the current run — needed by the
  // resume / rerun endpoints (they're keyed by message_id, not run_id).
  messageId: string | null
  // Raw draft graph snapshot used for hidden-node pass-through. When
  // null, the store treats every node as visible (back-compat).
  graphDict: RuntimeGraphDict | null
  nodes: Record<string, RuntimeNode>
  edges: Record<string, RuntimeEdge>
  // Insertion order so the canvas reveals nodes left-to-right rather
  // than ReactFlow's auto-layout deciding alphabetically.
  visibleOrder: string[]
  // Ids of nodes the user can interact with right now (paused for edit
  // OR human-input form open). Drives CR6's inline buttons.
  pausedNodeIds: string[]
  // Per-paused-node metadata extracted from the SSE pause reasons.
  pausedKinds: Record<string, PausedNodeKinds>
  // Plain assistant message accumulated from `event: message` chunks.
  // Surfaced as a banner above the canvas — covers LLM answers and
  // middleware bailouts (e.g. balance checks) that never start a
  // workflow run.
  messageAnswer: string
  messageEnded: boolean
  // For diagnostic only — exposed in the toolbar.
  lastEventAt: number | null
  // CR10 review fix: when a terminated rerun returns a new workflow_run_id
  // the page subscribes to that SSE topic. The store carries it as a
  // single-shot signal — page consumes it, then clears via
  // `consumePendingRerunRunId`.
  pendingRerunRunId: string | null

  applyEvent: (event: SSEEvent) => void
  setMessageId: (messageId: string | null) => void
  setGraphDict: (graph: RuntimeGraphDict | null) => void
  clearPause: (nodeId: string) => void
  signalRerunRunId: (runId: string) => void
  consumePendingRerunRunId: () => string | null
  // Replace per-node positions in bulk. Used by the elk-layout effect
  // in CanvasRuntimeInner to reflow the graph after each reveal so
  // branches stack vertically instead of being crammed into one row.
  relayoutNodes: (positions: Map<string, { x: number, y: number }>) => void
  reset: () => void
}

const _initialState = {
  workflowRunId: null,
  messageId: null as string | null,
  graphDict: null as RuntimeGraphDict | null,
  nodes: {} as Record<string, RuntimeNode>,
  edges: {} as Record<string, RuntimeEdge>,
  visibleOrder: [] as string[],
  pausedNodeIds: [] as string[],
  pausedKinds: {} as Record<string, PausedNodeKinds>,
  messageAnswer: '',
  messageEnded: false,
  lastEventAt: null as number | null,
  pendingRerunRunId: null as string | null,
}

// Lay nodes out left-to-right by their reveal order. The real workflow
// editor uses dagre — for the runtime a simple offset is enough until
// users ask for branching layouts.
// Matches runtime-node NODE_W (280) + ~40px gap so cards never overlap.
const _nodeOffset = 320
const _nodeY = 0

// CR9: a node is hidden from the canvas runtime when its draft graph
// data has show_in_canvas_runtime explicitly set to false. Default
// (undefined or true) means visible.
const _isHiddenInRuntime = (
  graph: RuntimeGraphDict | null,
  nodeId: string,
): boolean => {
  if (!graph)
    return false
  const node = graph.nodes.find(n => n.id === nodeId)
  return node?.data?.show_in_canvas_runtime === false
}

// CR9: pass-through edge expansion. From `source`, walk the draft
// graph and for each first-encountered visible successor emit an edge
// `source → successor`. Keeps the canvas connected even when
// intermediate nodes were hidden by the author.
const _visibleSuccessors = (
  graph: RuntimeGraphDict | null,
  source: string,
): string[] => {
  if (!graph)
    return []
  const visited = new Set<string>()
  const out: string[] = []
  const stack: string[] = [source]
  while (stack.length) {
    const cur = stack.pop()!
    for (const e of graph.edges) {
      if (e.source !== cur)
        continue
      if (visited.has(e.target))
        continue
      visited.add(e.target)
      if (_isHiddenInRuntime(graph, e.target))
        stack.push(e.target)
      else out.push(e.target)
    }
  }
  return out
}

// CR9: walk back from `start` through hidden ancestors and return
// the first visible predecessor on each branch. The SSE event only
// carries one predecessor_node_id, but a hidden node may itself have
// multiple visible parents in the draft graph — we don't lose them.
//
// `_seenNodes` is the runtime-store's `nodes` map; we use it to avoid
// proposing predecessors the engine hasn't reached this run yet.

const _resolveVisibleSources = (
  graph: RuntimeGraphDict | null,
  start: string,
  _seenNodes: Record<string, RuntimeNode>,
  _hidden: boolean,
): string[] => {
  if (!graph)
    return [start]
  if (!_isHiddenInRuntime(graph, start))
    return [start]
  const visited = new Set<string>()
  const out: string[] = []
  const stack: string[] = [start]
  while (stack.length) {
    const cur = stack.pop()!
    for (const e of graph.edges) {
      if (e.target !== cur)
        continue
      if (visited.has(e.source))
        continue
      visited.add(e.source)
      if (_isHiddenInRuntime(graph, e.source))
        stack.push(e.source)
      else out.push(e.source)
    }
  }
  return out
}

const _placeNode = (index: number) => ({
  x: index * _nodeOffset,
  y: _nodeY,
})

// CR1 emits pause reasons as the literal string "user_edit:<node_id>:<kinds>"
// where kinds is "input", "output", or "input,output". Anything else (e.g.
// HumanInputRequired payloads) is treated as a human-input pause.
const _parsePausedKindsFor = (
  nodeId: string,
  reasons: string[],
): PausedNodeKinds => {
  for (const raw of reasons) {
    if (typeof raw !== 'string')
      continue
    if (!raw.startsWith('user_edit:'))
      continue
    const [, encodedNode, encodedKinds = ''] = raw.split(':')
    if (encodedNode !== nodeId)
      continue
    const kinds = encodedKinds.split(',').filter(Boolean)
    return {
      source: 'user_edit',
      allowInput: kinds.includes('input'),
      allowOutput: kinds.includes('output'),
    }
  }
  // No matching user_edit reason — treat as a human-input pause; the
  // existing form flow is what unblocks it, not the M6 modal.
  return {
    source: 'human_input',
    allowInput: false,
    allowOutput: false,
  }
}

export const useRuntimeStore = create<RuntimeState>((set, get) => ({
  ..._initialState,

  applyEvent: (event) => {
    const now = Date.now()
    if (event.type === 'workflow_started') {
      // CR9: keep the graphDict across runs of the same canvas — the
      // visibility decision is per-canvas, not per-run, and refetching
      // it on every submit is wasteful.
      const { graphDict } = get()
      set({
        ..._initialState,
        graphDict,
        workflowRunId: event.workflowRunId,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'node_started') {
      const { nodes, edges, visibleOrder, graphDict } = get()
      const hidden = _isHiddenInRuntime(graphDict, event.nodeId)
      const existing = nodes[event.nodeId]
      // Hidden nodes still get tracked in `nodes` (so node_finished
      // can update their internal state and downstream lookups stay
      // correct) but are kept out of `visibleOrder` so the canvas
      // never renders a card for them.
      const nextOrder
        = existing || hidden ? visibleOrder : [...visibleOrder, event.nodeId]
      const nextNodes = {
        ...nodes,
        [event.nodeId]: {
          id: event.nodeId,
          type: event.nodeType,
          title: event.title,
          position:
            existing?.position
            ?? _placeNode(hidden ? visibleOrder.length : nextOrder.length - 1),
          status: 'running' as NodeRuntimeStatus,
          inputs: event.inputs,
          // Carry forward outputs if the engine restarts a node we've
          // seen before (e.g. retry).
          outputs: existing?.outputs,
        },
      }
      // CR9: edges connect VISIBLE source → VISIBLE target. If the
      // target is visible, walk back through hidden ancestors to find
      // the nearest visible predecessor (or just use the SSE-reported
      // predecessor when both ends are visible).
      //
      // Fallback chain when the engine doesn't supply predecessor_node_id
      // on the SSE event (some chatflow nodes don't set it):
      //   1. SSE-reported predecessor — most accurate when present.
      //   2. Last visible node in `visibleOrder` — true for linear
      //      chatflows, which covers ~all canvas-runtime app shapes.
      // The first node ever revealed (Start) has no predecessor in
      // either source — it's expected to be edgeless.
      const nextEdges = { ...edges }
      if (!hidden) {
        const candidatePred
          = event.predecessorNodeId
            || (visibleOrder.length > 0
              ? visibleOrder[visibleOrder.length - 1]
              : undefined)
        if (candidatePred && candidatePred !== event.nodeId) {
          const sources = _resolveVisibleSources(
            graphDict,
            candidatePred,
            nodes,
            hidden,
          )
          for (const src of sources) {
            if (!nextNodes[src])
              continue
            const edgeId = `${src}->${event.nodeId}`
            if (!nextEdges[edgeId]) {
              nextEdges[edgeId] = {
                id: edgeId,
                source: src,
                target: event.nodeId,
              }
            }
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
      const nextKinds: Record<string, PausedNodeKinds> = {}
      for (const id of paused) {
        nextNodes[id] = { ...nextNodes[id], status: 'paused' }
        nextKinds[id] = _parsePausedKindsFor(id, event.reasons)
      }
      set({
        nodes: nextNodes,
        pausedNodeIds: paused,
        pausedKinds: nextKinds,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'workflow_finished') {
      // Clear pause markers — finishing implies all pauses resolved.
      // Also flip any lingering 'paused' nodes back to 'succeeded' so
      // the canvas doesn't keep showing the orange badge on nodes that
      // have moved on (the engine doesn't re-emit node_finished for
      // nodes that were already finished before the pause).
      const { nodes, pausedNodeIds } = get()
      const nextNodes = { ...nodes }
      for (const id of pausedNodeIds) {
        if (nextNodes[id]?.status === 'paused')
          nextNodes[id] = { ...nextNodes[id], status: 'succeeded' }
      }
      set({
        nodes: nextNodes,
        pausedNodeIds: [],
        pausedKinds: {},
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'message') {
      // Append (or replace) the running answer buffer. Surfaced by the
      // page as a banner so users see middleware bailouts (e.g. balance
      // checks) and ad-hoc LLM answers even when no workflow node fires.
      const { messageAnswer } = get()
      const next
        = event.mode === 'replace' ? event.text : `${messageAnswer}${event.text}`
      set({
        messageAnswer: next,
        messageEnded: false,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'message_end') {
      set({ messageEnded: true, lastEventAt: now })
    }
  },

  setMessageId: messageId => set({ messageId }),

  setGraphDict: graphDict => set({ graphDict }),

  clearPause: (nodeId) => {
    // Flip the node back to 'succeeded' alongside dropping its pause
    // metadata. The engine's pause point is always *after* a successful
    // node finish, so 'succeeded' is the truthful state to restore.
    // If the resumed run later re-runs this node it will emit a fresh
    // node_started which overwrites this anyway.
    const { nodes, pausedNodeIds, pausedKinds } = get()
    const nextIds = pausedNodeIds.filter(id => id !== nodeId)
    const nextKinds = { ...pausedKinds }
    delete nextKinds[nodeId]
    const nextNodes = { ...nodes }
    if (nextNodes[nodeId]?.status === 'paused')
      nextNodes[nodeId] = { ...nextNodes[nodeId], status: 'succeeded' }
    set({
      nodes: nextNodes,
      pausedNodeIds: nextIds,
      pausedKinds: nextKinds,
    })
  },

  signalRerunRunId: runId => set({ pendingRerunRunId: runId }),

  consumePendingRerunRunId: () => {
    const id = get().pendingRerunRunId
    if (id)
      set({ pendingRerunRunId: null })
    return id
  },

  relayoutNodes: (positions) => {
    const { nodes } = get()
    let changed = false
    const next: Record<string, RuntimeNode> = {}
    for (const [id, n] of Object.entries(nodes)) {
      const p = positions.get(id)
      if (p && (p.x !== n.position.x || p.y !== n.position.y)) {
        next[id] = { ...n, position: { x: p.x, y: p.y } }
        changed = true
      }
      else {
        next[id] = n
      }
    }
    if (changed)
      set({ nodes: next })
  },

  reset: () => set({ ..._initialState }),
}))
