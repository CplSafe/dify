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
    // answer node). When the owning node hasn't been revealed yet
    // (message arrives before its node_started), the store stashes
    // the text in a pending buffer keyed by this id and flushes it
    // into outputs.answer the moment node_started fires.
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
  // Buffer for `event: message` chunks whose owning node hasn't been
  // revealed yet. Chatflow's SSE order is sometimes [message] →
  // [node_started for the answer node] → [node_finished], so the text
  // arrives BEFORE the card it should land on. Stash by node_id and
  // flush into outputs.answer the moment the matching node_started
  // fires.
  pendingMessageByNode: Record<string, string>

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
  pendingMessageByNode: {} as Record<string, string>,
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
      // Two distinct cases here:
      //   a) Fresh user-initiated run — reset the whole canvas.
      //   b) Resubscribe-replay (after human-input submit / CR10 rerun).
      //      The /workflow/<id>/events endpoint replays from the
      //      beginning, so workflow_started fires AGAIN with the same
      //      run id we already have. Wiping the canvas would erase
      //      the cards the user just watched run. Detect this case
      //      and only update lastEventAt instead.
      const { graphDict, workflowRunId } = get()
      if (workflowRunId === event.workflowRunId) {
        set({ lastEventAt: now })
        return
      }
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
      // On resubscribe replay, the same node_started fires again for
      // nodes we already finished. Keep their terminal status so the
      // user doesn't see green cards flicker back to running.
      const isReplay
        = existing
          && (existing.status === 'succeeded'
            || existing.status === 'failed'
            || existing.status === 'paused')
      let nextNodes: Record<string, RuntimeNode> = {
        ...nodes,
        [event.nodeId]: {
          id: event.nodeId,
          type: event.nodeType,
          title: event.title,
          position:
            existing?.position
            ?? _placeNode(hidden ? visibleOrder.length : nextOrder.length - 1),
          status: isReplay ? existing.status : ('running' as NodeRuntimeStatus),
          inputs: event.inputs ?? existing?.inputs,
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
      // Flush any pending message text that arrived before this
      // node was revealed (chatflow's SSE order is sometimes
      // [event:message for answer node] → [node_started for it]).
      const { pendingMessageByNode } = get()
      let nextPending = pendingMessageByNode
      const pending = pendingMessageByNode[event.nodeId]
      if (pending) {
        const target = nextNodes[event.nodeId]
        if (target) {
          nextNodes = {
            ...nextNodes,
            [event.nodeId]: {
              ...target,
              outputs: { ...(target.outputs ?? {}), answer: pending },
            },
          }
        }
        nextPending = { ...pendingMessageByNode }
        delete nextPending[event.nodeId]
      }

      set({
        nodes: nextNodes,
        edges: nextEdges,
        visibleOrder: nextOrder,
        pendingMessageByNode: nextPending,
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
      const { messageAnswer, nodes, visibleOrder, pendingMessageByNode }
        = get()
      const next
        = event.mode === 'replace' ? event.text : `${messageAnswer}${event.text}`

      // Route the chunk to the owning node's outputs.answer.
      //
      // Three cases, in priority order:
      //   1. event.nodeId provided + node already revealed → write to it.
      //   2. event.nodeId provided + node NOT yet revealed → stash in
      //      pendingMessageByNode; node_started will flush later.
      //   3. event.nodeId missing → walk visibleOrder back, find the
      //      latest answer/llm node (works for old payloads that don't
      //      carry from_variable_selector).
      let nextNodes = nodes
      let nextPending = pendingMessageByNode
      const writeToNode = (id: string) => {
        const n = nodes[id]
        if (!n)
          return false
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
        return true
      }

      if (event.nodeId) {
        if (!writeToNode(event.nodeId)) {
          // Stash for the upcoming node_started.
          const prev = pendingMessageByNode[event.nodeId] ?? ''
          const buffered
            = event.mode === 'replace' ? event.text : `${prev}${event.text}`
          nextPending = { ...pendingMessageByNode, [event.nodeId]: buffered }
        }
      }
      else {
        for (let i = visibleOrder.length - 1; i >= 0; i--) {
          const id = visibleOrder[i]
          const n = nodes[id]
          if (!n)
            continue
          if (n.type !== 'answer' && n.type !== 'llm')
            continue
          writeToNode(id)
          break
        }
      }

      set({
        messageAnswer: next,
        messageEnded: false,
        nodes: nextNodes,
        pendingMessageByNode: nextPending,
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
