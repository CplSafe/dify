'use client'

import type { HumanInputFormData } from '@/types/workflow'
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
    // First entry of `from_variable_selector` from the SSE payload —
    // identifies which workflow node owns this chunk (typically the
    // answer node). Lets the store route the text into that node's
    // outputs.answer instead of guessing by visibleOrder.
    nodeId?: string
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
    type?: string
    title?: string
    data?: {
      show_in_canvas_runtime?: boolean
      allow_user_edit_input?: boolean
      allow_user_edit_output?: boolean
    }
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
  // Active human-input forms keyed by node_id. Populated when the
  // engine emits `human_input_required` and cleared when the user
  // submits or the form expires. The card uses presence here to swap
  // its CTA for "等待你输入" and the drawer mounts off the same data.
  humanInputForms: Record<string, HumanInputFormData>
  // The node whose human-input drawer is currently open. Set by the
  // card CTA, cleared by the drawer close handler. Kept in the store
  // (instead of local state on the canvas root) so any component can
  // open the drawer without prop-drilling.
  openHumanInputNodeId: string | null

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
  // Human-input lifecycle.
  setHumanInputForm: (form: HumanInputFormData) => void
  clearHumanInputForm: (nodeId: string) => void
  openHumanInputDrawer: (nodeId: string) => void
  closeHumanInputDrawer: () => void
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
  humanInputForms: {} as Record<string, HumanInputFormData>,
  openHumanInputNodeId: null as string | null,
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
      // Mode A: cards came from setGraphDict at page mount, so the
      // canvas is already populated. A new workflow run only needs to
      // reset per-node status / outputs (clear messageAnswer, paused
      // markers, etc) — the node + edge layout stays put.
      const { nodes, edges, visibleOrder, graphDict } = get()
      const resetNodes: Record<string, RuntimeNode> = {}
      for (const [id, n] of Object.entries(nodes)) {
        resetNodes[id] = {
          ...n,
          status: 'pending',
          outputs: undefined,
          error: undefined,
        }
      }
      set({
        ..._initialState,
        graphDict,
        nodes: resetNodes,
        edges,
        visibleOrder,
        workflowRunId: event.workflowRunId,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'node_started') {
      // Mode A: only update the pre-existing card's status. Nodes that
      // weren't in the draft graph (e.g. dynamically inserted by an
      // iteration) get inserted lazily as a fallback so we don't lose
      // them entirely.
      const { nodes, edges, visibleOrder, graphDict } = get()
      const hidden = _isHiddenInRuntime(graphDict, event.nodeId)
      if (hidden) {
        // Hidden nodes don't render — track them so node_finished can
        // still update internal state, but stay out of visibleOrder.
        set({
          nodes: {
            ...nodes,
            [event.nodeId]: {
              id: event.nodeId,
              type: event.nodeType,
              title: event.title,
              position: _placeNode(visibleOrder.length),
              status: 'running' as NodeRuntimeStatus,
              inputs: event.inputs,
              outputs: nodes[event.nodeId]?.outputs,
            },
          },
          lastEventAt: now,
        })
        return
      }
      const existing = nodes[event.nodeId]
      const nextNodes = {
        ...nodes,
        [event.nodeId]: existing
          ? {
              ...existing,
              // Refresh the title in case the draft was updated since
              // the graph was loaded.
              title: existing.title || event.title,
              type: existing.type || event.nodeType,
              status: 'running' as NodeRuntimeStatus,
              inputs: event.inputs ?? existing.inputs,
              // Reset outputs/error on a fresh start; they'll be
              // overwritten by the matching node_finished.
              outputs: undefined,
              error: undefined,
            }
          : {
              // Fallback for nodes that weren't in the draft graph
              // (e.g. iteration children). Append to visibleOrder.
              id: event.nodeId,
              type: event.nodeType,
              title: event.title,
              position: _placeNode(visibleOrder.length),
              status: 'running' as NodeRuntimeStatus,
              inputs: event.inputs,
            },
      }
      const nextOrder = existing
        ? visibleOrder
        : [...visibleOrder, event.nodeId]
      // Edges are pre-built by setGraphDict in mode A, so we don't
      // synthesize them on node_started anymore. Lazy fallback nodes
      // get a best-effort edge from the previous visible node.
      let nextEdges = edges
      if (!existing && visibleOrder.length > 0) {
        const src = visibleOrder[visibleOrder.length - 1]
        const id = `${src}->${event.nodeId}`
        if (!edges[id]) {
          nextEdges = {
            ...edges,
            [id]: { id, source: src, target: event.nodeId },
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
      const { messageAnswer, nodes, visibleOrder } = get()
      const next
        = event.mode === 'replace' ? event.text : `${messageAnswer}${event.text}`

      // Attach the message text to the owning node's outputs.answer.
      // Preferred path: SSE's `from_variable_selector[0]` tells us
      // exactly which node (mode A — cards exist for every node from
      // setGraphDict, so we can target by id). Fallback: walk visible
      // order looking for the latest answer/llm node (covers cases
      // where the engine omitted the selector).
      let nextNodes = nodes
      const targetId = event.nodeId
        ? nodes[event.nodeId]
          ? event.nodeId
          : null
        : null
      const writeTo = (id: string) => {
        const n = nodes[id]
        if (!n)
          return
        const prevAnswer = (n.outputs?.answer as string | undefined) ?? ''
        const newAnswer
          = event.mode === 'replace' ? event.text : `${prevAnswer}${event.text}`
        nextNodes = {
          ...nodes,
          [id]: {
            ...n,
            outputs: { ...(n.outputs ?? {}), answer: newAnswer },
          },
        }
      }
      if (targetId) {
        writeTo(targetId)
      }
      else {
        for (let i = visibleOrder.length - 1; i >= 0; i--) {
          const id = visibleOrder[i]
          const n = nodes[id]
          if (!n)
            continue
          if (n.type !== 'answer' && n.type !== 'llm')
            continue
          writeTo(id)
          break
        }
      }

      set({
        messageAnswer: next,
        messageEnded: false,
        nodes: nextNodes,
        lastEventAt: now,
      })
      return
    }

    if (event.type === 'message_end') {
      set({ messageEnded: true, lastEventAt: now })
    }
  },

  setMessageId: messageId => set({ messageId }),

  setGraphDict: (graphDict) => {
    // Mode A: render the FULL workflow up-front from the draft graph,
    // so cards exist before any SSE event fires. Subsequent
    // node_started / node_finished events only mutate `status` and
    // `outputs` on the pre-existing entries — they never insert new
    // nodes / edges.
    if (!graphDict) {
      set({ graphDict: null })
      return
    }
    const visibleNodes = graphDict.nodes.filter(
      n => n.data?.show_in_canvas_runtime !== false,
    )
    const nextNodes: Record<string, RuntimeNode> = {}
    const visibleOrder: string[] = []
    visibleNodes.forEach((n, idx) => {
      visibleOrder.push(n.id)
      nextNodes[n.id] = {
        id: n.id,
        type: n.type ?? '',
        title: n.title ?? '',
        position: _placeNode(idx),
        status: 'pending',
      }
    })
    // Pre-build edges from the draft graph too (CR9 already had the
    // hidden-node pass-through machinery; reuse it so edges connect
    // visible source → visible target only).
    const visibleIds = new Set(visibleOrder)
    const nextEdges: Record<string, RuntimeEdge> = {}
    for (const e of graphDict.edges) {
      if (!visibleIds.has(e.source) || !visibleIds.has(e.target)) {
        // At least one end is hidden — expand via pass-through. The
        // existing helpers _resolveVisibleSources / _visibleSuccessors
        // return the nearest visible neighbours on each side.
        const sources = visibleIds.has(e.source)
          ? [e.source]
          : _resolveVisibleSources(graphDict, e.source, nextNodes, true)
        const targets = visibleIds.has(e.target)
          ? [e.target]
          : _visibleSuccessors(graphDict, e.target)
        for (const src of sources) {
          for (const tgt of targets) {
            const id = `${src}->${tgt}`
            nextEdges[id] = { id, source: src, target: tgt }
          }
        }
        continue
      }
      const id = `${e.source}->${e.target}`
      nextEdges[id] = { id, source: e.source, target: e.target }
    }
    set({
      graphDict,
      nodes: nextNodes,
      edges: nextEdges,
      visibleOrder,
    })
  },

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

  setHumanInputForm: (form) => {
    const { humanInputForms } = get()
    set({
      humanInputForms: { ...humanInputForms, [form.node_id]: form },
    })
  },

  clearHumanInputForm: (nodeId) => {
    const {
      humanInputForms,
      openHumanInputNodeId,
      nodes,
      pausedNodeIds,
      pausedKinds,
    } = get()
    if (!(nodeId in humanInputForms))
      return
    const nextForms = { ...humanInputForms }
    delete nextForms[nodeId]
    // Submitted/timed-out human-input also exits the paused state. The
    // engine will follow up with `node_finished` shortly, but flipping
    // status here removes the amber pulse + CTA the moment the user
    // hits submit so the UI feels responsive instead of stuck.
    const nextNodes = { ...nodes }
    if (nextNodes[nodeId]?.status === 'paused')
      nextNodes[nodeId] = { ...nextNodes[nodeId], status: 'succeeded' }
    const nextPausedIds = pausedNodeIds.filter(id => id !== nodeId)
    const nextPausedKinds = { ...pausedKinds }
    delete nextPausedKinds[nodeId]
    set({
      humanInputForms: nextForms,
      openHumanInputNodeId:
        openHumanInputNodeId === nodeId ? null : openHumanInputNodeId,
      nodes: nextNodes,
      pausedNodeIds: nextPausedIds,
      pausedKinds: nextPausedKinds,
    })
  },

  openHumanInputDrawer: nodeId => set({ openHumanInputNodeId: nodeId }),
  closeHumanInputDrawer: () => set({ openHumanInputNodeId: null }),

  reset: () => set({ ..._initialState }),
}))
