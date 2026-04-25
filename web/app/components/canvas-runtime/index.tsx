'use client'

import type { Edge, Node } from 'reactflow'
import type { RuntimeNode } from './runtime-store'
import { useMemo } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  MiniMap,
  ReactFlowProvider,
} from 'reactflow'
import { RuntimeContext } from './runtime-context'
import RuntimeNodeComponent from './runtime-node'
import { useRuntimeStore } from './runtime-store'
import RuntimeToolbar from './toolbar'
import 'reactflow/dist/style.css'

const NODE_TYPES = {
  runtime: RuntimeNodeComponent,
}

type CanvasRuntimeProps = {
  // CR6 needs the appId to call resume / rerun endpoints from inside
  // node-level pause CTAs.
  appId: string
  // CR7 will pass through; CR4 forwards as-is.
  onSave?: () => void
  // CR5 will mount its bottom-centred input as a child so it sits above
  // the canvas without hijacking ReactFlow's pointer events.
  children?: React.ReactNode
}

const CanvasRuntimeInner = ({ onSave, children }: CanvasRuntimeProps) => {
  const storeNodes = useRuntimeStore(s => s.nodes)
  const storeEdges = useRuntimeStore(s => s.edges)
  const visibleOrder = useRuntimeStore(s => s.visibleOrder)

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
        type: 'smoothstep',
        animated: storeNodes[e.target]?.status === 'running',
      })),
    [storeEdges, storeNodes],
  )

  // Drive ReactFlow directly off the projected store output. ReactFlow
  // accepts controlled `nodes` / `edges` props and we don't need any of
  // its internal change tracking (no drag, no connect, no delete).
  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={reactFlowNodes}
        edges={reactFlowEdges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.4 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        deleteKeyCode={null}
        multiSelectionKeyCode={null}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
        <MiniMap
          pannable
          zoomable
          className="!right-4 !bottom-32 !rounded-lg !border !border-components-panel-border !bg-components-panel-bg !shadow-md"
        />
      </ReactFlow>
      <RuntimeToolbar onSave={onSave} />
      {children}
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
