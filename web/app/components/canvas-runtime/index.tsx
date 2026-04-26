'use client'

import type { Edge, Node } from 'reactflow'
import type { RuntimeNode } from './runtime-store'
import { useEffect, useMemo } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlowProvider,
} from 'reactflow'
import { RuntimeContext } from './runtime-context'
import RuntimeEdge from './runtime-edge'
import { computeRuntimeLayout } from './runtime-layout'
import RuntimeNodeComponent from './runtime-node'
import { useRuntimeStore } from './runtime-store'
import RuntimeToolbar from './toolbar'
import 'reactflow/dist/style.css'

// Match the fixed footprint declared in runtime-node.tsx so the elk
// layouter reserves the right amount of room around each card.
const NODE_W = 280
const NODE_H = 224

const NODE_TYPES = {
  runtime: RuntimeNodeComponent,
}

const EDGE_TYPES = {
  runtime: RuntimeEdge,
}

type CanvasRuntimeProps = {
  // CR6 needs the appId to call resume / rerun endpoints from inside
  // node-level pause CTAs.
  appId: string
  // CR7: opens the save-as-canvas dialog. saveDisabled lets the page
  // grey the button out (e.g. before the user has run anything).
  onSave?: () => void
  saveDisabled?: boolean
  // CR5 will mount its bottom-centred input as a child so it sits above
  // the canvas without hijacking ReactFlow's pointer events.
  children?: React.ReactNode
}

const CanvasRuntimeInner = ({
  onSave,
  saveDisabled,
  children,
}: CanvasRuntimeProps) => {
  const storeNodes = useRuntimeStore(s => s.nodes)
  const storeEdges = useRuntimeStore(s => s.edges)
  const visibleOrder = useRuntimeStore(s => s.visibleOrder)
  const relayoutNodes = useRuntimeStore(s => s.relayoutNodes)

  // Reflow the canvas via ELK (layered/Sugiyama, same family as dagre)
  // every time a node is revealed or an edge is added. The store's
  // initial _placeNode() lays cards on a single horizontal line, which
  // works for purely linear flows but breaks down on branching
  // chatflows. ELK gives us proper layered placement with vertical
  // offsetting, edge crossing minimisation, and centred parents.
  //
  // Keys are concatenated id strings so React only re-runs the effect
  // when the topology actually changes — node *status* updates (which
  // happen far more often) don't retrigger layout.
  const layoutKey = useMemo(
    () =>
      `${visibleOrder.join(',')}|${Object.keys(storeEdges).sort().join(',')}`,
    [visibleOrder, storeEdges],
  )

  useEffect(() => {
    if (visibleOrder.length === 0)
      return
    let cancelled = false
    void (async () => {
      try {
        const positions = await computeRuntimeLayout({
          nodes: visibleOrder.map(id => ({ id })),
          edges: Object.values(storeEdges).map(e => ({
            id: e.id,
            source: e.source,
            target: e.target,
          })),
          nodeWidth: NODE_W,
          nodeHeight: NODE_H,
        })
        if (!cancelled)
          relayoutNodes(positions)
      }
      catch (err) {
        // ELK failures are non-fatal — the store keeps the linear
        // fallback positions so the user still sees their cards.
        console.warn('[canvas-runtime] elk layout failed', err)
      }
    })()
    return () => {
      cancelled = true
    }
    // layoutKey already encodes visibleOrder + storeEdges; depending on
    // the raw maps would re-fire on every status update too.
    // eslint-disable-next-line react/exhaustive-deps
  }, [layoutKey])

  // Project the store into ReactFlow's node/edge shape. Order matters
  // so newly-revealed nodes are appended (no auto-relayout flicker).
  const reactFlowNodes = useMemo<Node<RuntimeNode>[]>(
    () =>
      visibleOrder
        .map<Node<RuntimeNode> | null>((id) => {
          const n = storeNodes[id]
          if (!n)
            return null
          return {
            id: n.id,
            type: 'runtime',
            position: n.position,
            data: n,
            // Read-only: prevent every interaction the editor canvas
            // would normally allow.
            draggable: false,
            selectable: true,
            connectable: false,
            deletable: false,
          }
        })
        .filter((n): n is Node<RuntimeNode> => n !== null),
    [storeNodes, visibleOrder],
  )

  const reactFlowEdges = useMemo<Edge[]>(
    () =>
      Object.values(storeEdges).map(e => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
        // Custom edge owns its own gradient + flow animation, so the
        // built-in `animated` flag is no longer needed (and would draw
        // a second dashed overlay on top of ours).
        type: 'runtime',
      })),
    [storeEdges],
  )

  // Drive ReactFlow directly off the projected store output. ReactFlow
  // accepts controlled `nodes` / `edges` props and we don't need any of
  // its internal change tracking (no drag, no connect, no delete).
  //
  // Outer wrapper paints a deep tech-y backdrop:
  //   - vertical gradient from near-black to slate
  //   - subtle radial cyan/indigo glows in the corners ("data centre" vibe)
  // ReactFlow's <Background> dots are recoloured via CSS to match.
  return (
    <div className="canvas-runtime-stage relative h-full w-full overflow-hidden">
      <ReactFlow
        nodes={reactFlowNodes}
        edges={reactFlowEdges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.4 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        deleteKeyCode={null}
        multiSelectionKeyCode={null}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1.2}
          color="rgba(148, 163, 184, 0.18)"
        />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(15, 23, 42, 0.6)"
          nodeColor="#22d3ee"
          className="!right-4 !bottom-32 !rounded-xl !border !border-cyan-400/20 !bg-slate-950/70 !shadow-lg !shadow-cyan-500/10 !backdrop-blur"
        />
      </ReactFlow>
      <RuntimeToolbar onSave={onSave} saveDisabled={saveDisabled} />
      {children}
      <style jsx>
        {`
          .canvas-runtime-stage {
            background:
              radial-gradient(
                circle at 12% 18%,
                rgba(34, 211, 238, 0.18),
                transparent 55%
              ),
              radial-gradient(
                circle at 88% 80%,
                rgba(99, 102, 241, 0.18),
                transparent 55%
              ),
              linear-gradient(180deg, #050816 0%, #0b1124 60%, #0a0f1f 100%);
          }
        `}
      </style>
    </div>
  )
}

const CanvasRuntime = (props: CanvasRuntimeProps) => {
  const ctx = useMemo(() => ({ appId: props.appId }), [props.appId])
  return (
    <RuntimeContext value={ctx}>
      <ReactFlowProvider>
        <CanvasRuntimeInner {...props} />
      </ReactFlowProvider>
    </RuntimeContext>
  )
}

export default CanvasRuntime
