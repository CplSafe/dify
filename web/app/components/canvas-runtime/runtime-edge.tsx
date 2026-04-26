'use client'

import type { FC } from 'react'
import type { EdgeProps } from 'reactflow'
import { BaseEdge, getSmoothStepPath } from 'reactflow'
import { useRuntimeStore } from './runtime-store'

/**
 * Tech-flavoured edge for the canvas runtime.
 *
 * The line itself is a smooth-step path drawn with a per-edge SVG
 * `<linearGradient>` (cyan → indigo → magenta) so adjacent edges read
 * as distinct flows rather than a tangled web. When the downstream
 * node is currently running we overlay a dashed stroke and animate
 * `stroke-dashoffset` to suggest data flowing along the wire — the
 * same idiom most "agent runtime" canvases use to telegraph activity.
 *
 * Colour shifts with the downstream node's status:
 *   - failed  → magenta/red, no animation
 *   - paused  → amber, no animation
 *   - running → bright accent + animated dashes
 *   - default → cool blue/indigo at low opacity
 */
const RuntimeEdge: FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  target,
  markerEnd,
}) => {
  const targetStatus = useRuntimeStore(s => s.nodes[target]?.status)
  const [path] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 18,
  })

  // Pick the gradient stops based on the downstream node's status. Each
  // edge gets its own gradient id so React Flow's SVG <defs> stay
  // collision-free across many concurrent edges.
  const gradientId = `runtime-edge-${id}`
  const stops = (() => {
    if (targetStatus === 'failed')
      return ['#f43f5e', '#dc2626']
    if (targetStatus === 'paused')
      return ['#f59e0b', '#d97706']
    if (targetStatus === 'running')
      return ['#22d3ee', '#6366f1']
    if (targetStatus === 'succeeded')
      return ['#34d399', '#22d3ee']
    // pending / unknown
    return ['#475569', '#334155']
  })()

  const isActive = targetStatus === 'running'
  const baseOpacity = targetStatus === 'pending' ? 0.4 : 0.85

  return (
    <>
      <defs>
        <linearGradient
          id={gradientId}
          x1={sourceX}
          y1={sourceY}
          x2={targetX}
          y2={targetY}
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor={stops[0]} stopOpacity={baseOpacity} />
          <stop offset="100%" stopColor={stops[1]} stopOpacity={baseOpacity} />
        </linearGradient>
      </defs>

      {/* Soft outer glow — drawn first so the bright line sits on top. */}
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: stops[0],
          strokeWidth: 6,
          strokeOpacity: isActive ? 0.35 : 0.12,
          filter: 'blur(2px)',
          pointerEvents: 'none',
        }}
      />

      {/* Solid gradient line. */}
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: `url(#${gradientId})`,
          strokeWidth: 2,
          strokeLinecap: 'round',
        }}
      />

      {/* Animated flow overlay — only painted for running edges. */}
      {isActive && (
        <path
          d={path}
          fill="none"
          stroke={stops[0]}
          strokeWidth={2}
          strokeLinecap="round"
          strokeDasharray="6 12"
          opacity={0.9}
          style={{ animation: 'runtimeEdgeFlow 1.2s linear infinite' }}
        />
      )}

      <style jsx>
        {`
        @keyframes runtimeEdgeFlow {
          to {
            stroke-dashoffset: -36;
          }
        }
      `}
      </style>
    </>
  )
}

export default RuntimeEdge
