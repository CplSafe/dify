'use client'

import type { FC } from 'react'
import type { NodeProps } from 'reactflow'
import type { NodeRuntimeStatus, RuntimeNode } from './runtime-store'
import type { BlockEnum } from '@/app/components/workflow/types'
import {
  RiAlertFill,
  RiCheckboxCircleFill,
  RiErrorWarningFill,
  RiLoader2Line,
  RiPauseCircleFill,
  RiTimeLine,
} from '@remixicon/react'
import { useMemo } from 'react'
import { Handle, Position } from 'reactflow'
import BlockIcon from '@/app/components/workflow/block-icon'
import { cn } from '@/utils/classnames'
import { useRuntimeContext } from './runtime-context'
import RuntimePauseActions from './runtime-pause-actions'
import RuntimeRerunActions from './runtime-rerun-actions'
import { useRuntimeStore } from './runtime-store'

// Fixed node footprint — every card is the same size so the canvas
// reads as a deliberate flow rather than a wall of inconsistently
// sized boxes. Inline content (title, type, summary) truncates;
// hover state surfaces actions without changing geometry.
const NODE_W = 260
const NODE_H = 132

// Status drives a subtle left accent bar + the trailing badge icon.
// Backgrounds stay panel-bg across the board so the canvas reads
// uniformly; the eye picks out colour from the accent + icon pair.
const STATUS_ACCENT: Record<NodeRuntimeStatus, string> = {
  pending: 'bg-divider-regular',
  running: 'bg-components-button-primary-bg',
  succeeded: 'bg-text-success',
  failed: 'bg-text-destructive',
  paused: 'bg-text-warning-secondary',
}

const STATUS_LABEL: Record<NodeRuntimeStatus, string> = {
  pending: '等待中',
  running: '运行中',
  succeeded: '完成',
  failed: '失败',
  paused: '已暂停',
}

const StatusBadge: FC<{ status: NodeRuntimeStatus }> = ({ status }) => {
  const cls = 'h-3.5 w-3.5 shrink-0'
  if (status === 'running') {
    return (
      <RiLoader2Line className={cn(cls, 'animate-spin text-text-accent')} />
    )
  }
  if (status === 'succeeded')
    return <RiCheckboxCircleFill className={cn(cls, 'text-text-success')} />
  if (status === 'failed')
    return <RiErrorWarningFill className={cn(cls, 'text-text-destructive')} />
  if (status === 'paused') {
    return (
      <RiPauseCircleFill className={cn(cls, 'text-text-warning-secondary')} />
    )
  }
  if (status === 'pending')
    return <RiTimeLine className={cn(cls, 'text-text-quaternary')} />
  return <RiAlertFill className={cn(cls, 'text-text-tertiary')} />
}

const _outputPreview = (outputs?: Record<string, unknown>): string => {
  if (!outputs)
    return ''
  // Prefer `text` / `result` / `answer` for readability; otherwise
  // serialise the first value we see.
  for (const k of ['text', 'answer', 'result', 'output']) {
    const v = outputs[k]
    if (typeof v === 'string')
      return v
  }
  for (const v of Object.values(outputs)) {
    if (typeof v === 'string')
      return v
    if (typeof v === 'number' || typeof v === 'boolean')
      return String(v)
  }
  try {
    return JSON.stringify(outputs)
  }
  catch {
    return ''
  }
}

const RuntimeNodeComponent: FC<NodeProps<RuntimeNode>> = ({ data }) => {
  const ctx = useRuntimeContext()
  const pausedKinds = useRuntimeStore(s => s.pausedKinds[data.id])
  const graphDict = useRuntimeStore(s => s.graphDict)
  // Show inline pause CTAs only for user_edit pauses; human_input pauses
  // surface their own form via the existing chatflow infrastructure.
  const showPauseActions
    = data.status === 'paused'
      && pausedKinds?.source === 'user_edit'
      && ctx?.appId

  // CR10: 重跑 actions on succeeded nodes. The author opts a node in via
  // the `allow_user_edit_input/output` toggles in the workflow editor;
  // those flags ride along on the runtime-graph projection (graphDict).
  const editAllow = useMemo(() => {
    if (!graphDict)
      return { input: false, output: false }
    const node = graphDict.nodes?.find(n => n.id === data.id)
    const nodeData = (node?.data ?? {}) as Record<string, unknown>
    return {
      input: nodeData.allow_user_edit_input === true,
      output: nodeData.allow_user_edit_output === true,
    }
  }, [graphDict, data.id])

  const showRerunActions
    = data.status === 'succeeded'
      && ctx?.appId
      && (editAllow.input || editAllow.output)

  const summary = useMemo(() => {
    if (data.error)
      return data.error
    return _outputPreview(data.outputs)
  }, [data.error, data.outputs])

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-2xl border border-divider-subtle bg-components-panel-bg shadow-sm transition-shadow hover:shadow-md',
      )}
      style={{ width: NODE_W, minHeight: NODE_H }}
      data-testid={`runtime-node-${data.id}`}
      data-status={data.status}
    >
      {/* status accent bar on the left */}
      <span
        aria-hidden
        className={cn(
          'absolute top-0 bottom-0 left-0 w-1',
          STATUS_ACCENT[data.status],
        )}
      />

      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !bg-divider-regular"
      />

      <div className="flex h-full flex-col gap-2 px-3 py-2.5 pl-4">
        <div className="flex items-center gap-2">
          <BlockIcon
            size="sm"
            type={data.type as BlockEnum}
            className="shrink-0"
          />
          <div className="min-w-0 grow">
            <div className="truncate system-sm-semibold text-text-primary">
              {data.title || data.id}
            </div>
            <div className="truncate system-2xs-regular text-text-tertiary">
              {data.type}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <StatusBadge status={data.status} />
            <span className="system-2xs-regular text-text-tertiary">
              {STATUS_LABEL[data.status]}
            </span>
          </div>
        </div>

        {summary && (
          <div
            className={cn(
              'line-clamp-2 system-xs-regular',
              data.error ? 'text-text-destructive' : 'text-text-secondary',
            )}
          >
            {summary}
          </div>
        )}

        {showPauseActions && pausedKinds && ctx && (
          <div className="mt-auto">
            <RuntimePauseActions
              appId={ctx.appId}
              node={data}
              kinds={pausedKinds}
            />
          </div>
        )}

        {showRerunActions && ctx && (
          <div className="mt-auto">
            <RuntimeRerunActions
              installedAppId={ctx.appId}
              node={data}
              allowInput={editAllow.input}
              allowOutput={editAllow.output}
            />
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !bg-divider-regular"
      />
    </div>
  )
}

export default RuntimeNodeComponent
