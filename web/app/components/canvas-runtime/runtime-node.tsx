'use client'

import type { FC } from 'react'
import type { NodeProps } from 'reactflow'
import type { NodeRuntimeStatus, RuntimeNode } from './runtime-store'
import type { BlockEnum } from '@/app/components/workflow/types'
import {
  RiCheckboxCircleFill,
  RiErrorWarningFill,
  RiLoader2Line,
  RiPauseCircleFill,
} from '@remixicon/react'
import { Handle, Position } from 'reactflow'
import BlockIcon from '@/app/components/workflow/block-icon'
import { cn } from '@/utils/classnames'

const STATUS_BORDER: Record<NodeRuntimeStatus, string> = {
  pending: 'border-divider-subtle',
  running: 'border-components-button-primary-border',
  succeeded: 'border-divider-subtle',
  failed: 'border-state-destructive-border',
  paused: 'border-state-warning-border',
}

const STATUS_BG: Record<NodeRuntimeStatus, string> = {
  pending: 'bg-components-panel-bg',
  running: 'bg-state-accent-hover-alt',
  succeeded: 'bg-components-panel-bg',
  failed: 'bg-state-destructive-hover',
  paused: 'bg-state-warning-hover',
}

const StatusBadge: FC<{ status: NodeRuntimeStatus }> = ({ status }) => {
  if (status === 'running') {
    return (
      <RiLoader2Line className="h-4 w-4 shrink-0 animate-spin text-text-accent" />
    )
  }
  if (status === 'succeeded') {
    return (
      <RiCheckboxCircleFill className="h-4 w-4 shrink-0 text-text-success" />
    )
  }
  if (status === 'failed') {
    return (
      <RiErrorWarningFill className="h-4 w-4 shrink-0 text-text-destructive" />
    )
  }
  if (status === 'paused') {
    return (
      <RiPauseCircleFill className="h-4 w-4 shrink-0 text-text-warning-secondary" />
    )
  }
  return null
}

/**
 * Runtime node renderer.
 *
 * Read-only by design: no drag, no delete, no inline config. The node
 * only ever shows status + title; CR6 layers the "继续 / 编辑后继续"
 * portal on paused nodes, and CR4 keeps this file ignorant of those
 * concerns to keep status rendering trivial to test.
 */
const RuntimeNodeComponent: FC<NodeProps<RuntimeNode>> = ({ data }) => {
  return (
    <div
      className={cn(
        'min-w-[180px] rounded-xl border-[1.5px] px-3 py-2 shadow-sm transition-colors',
        STATUS_BORDER[data.status],
        STATUS_BG[data.status],
      )}
      data-testid={`runtime-node-${data.id}`}
      data-status={data.status}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <div className="flex items-center gap-2">
        <BlockIcon
          size="sm"
          type={data.type as BlockEnum}
          className="shrink-0"
        />
        <div className="grow truncate system-sm-medium text-text-primary">
          {data.title}
        </div>
        <StatusBadge status={data.status} />
      </div>
      {data.error && (
        <div className="mt-1 system-xs-regular text-text-destructive">
          {data.error}
        </div>
      )}
      <Handle type="source" position={Position.Right} className="opacity-0" />
    </div>
  )
}

export default RuntimeNodeComponent
