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
import NodeMediaPreview from './runtime-node-media'
import RuntimePauseActions from './runtime-pause-actions'
import RuntimeRerunActions from './runtime-rerun-actions'
import { useRuntimeStore } from './runtime-store'

// Fixed node footprint — every card is the same size so the canvas
// reads as a deliberate flow rather than a wall of inconsistently
// sized boxes. Inline content (title, type, summary, media preview)
// truncates / scrolls inside the fixed box; hover state surfaces
// actions without changing geometry.
const NODE_W = 280
const NODE_H = 224

// Status drives the per-card neon accent. Card surface itself stays a
// uniform glassy slate so the eye picks out activity from the colour
// of the rim glow + status badge, not from card-to-card chrome drift.
const STATUS_ACCENT: Record<NodeRuntimeStatus, string> = {
  pending: 'from-slate-500/20 to-slate-700/20',
  running: 'from-cyan-400/60 to-indigo-500/60',
  succeeded: 'from-emerald-400/55 to-cyan-400/55',
  failed: 'from-rose-500/60 to-fuchsia-500/60',
  paused: 'from-amber-400/55 to-orange-500/55',
}

const STATUS_GLOW: Record<NodeRuntimeStatus, string> = {
  pending: 'shadow-[0_0_0_1px_rgba(148,163,184,0.18)]',
  running:
    'shadow-[0_0_0_1px_rgba(34,211,238,0.45),0_18px_55px_-15px_rgba(34,211,238,0.55)]',
  succeeded:
    'shadow-[0_0_0_1px_rgba(52,211,153,0.35),0_18px_55px_-20px_rgba(52,211,153,0.45)]',
  failed:
    'shadow-[0_0_0_1px_rgba(244,63,94,0.45),0_18px_55px_-15px_rgba(244,63,94,0.45)]',
  paused:
    'shadow-[0_0_0_1px_rgba(245,158,11,0.4),0_18px_55px_-15px_rgba(245,158,11,0.45)]',
}

const STATUS_TEXT: Record<NodeRuntimeStatus, string> = {
  pending: 'text-slate-400',
  running: 'text-cyan-300',
  succeeded: 'text-emerald-300',
  failed: 'text-rose-300',
  paused: 'text-amber-300',
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
  if (status === 'running')
    return <RiLoader2Line className={cn(cls, 'animate-spin text-cyan-300')} />
  if (status === 'succeeded')
    return <RiCheckboxCircleFill className={cn(cls, 'text-emerald-300')} />
  if (status === 'failed')
    return <RiErrorWarningFill className={cn(cls, 'text-rose-300')} />
  if (status === 'paused')
    return <RiPauseCircleFill className={cn(cls, 'text-amber-300')} />
  if (status === 'pending')
    return <RiTimeLine className={cn(cls, 'text-slate-400')} />
  return <RiAlertFill className={cn(cls, 'text-slate-400')} />
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
  const humanInputForm = useRuntimeStore(s => s.humanInputForms[data.id])
  const openHumanInputDrawer = useRuntimeStore(s => s.openHumanInputDrawer)
  // Show inline pause CTAs only for user_edit pauses; human_input pauses
  // surface their own "等待你输入" CTA which pops the side drawer.
  const showPauseActions
    = data.status === 'paused'
      && pausedKinds?.source === 'user_edit'
      && ctx?.appId
  // Human-input CTA: only meaningful when we have a real form payload
  // from the SSE event (token + inputs). A bare paused-state without
  // form data means the engine is still preparing; render nothing
  // rather than a dead button.
  const showHumanInputCta
    = data.status === 'paused'
      && pausedKinds?.source === 'human_input'
      && humanInputForm
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
        'group relative overflow-hidden rounded-2xl backdrop-blur-xl transition-all duration-300',
        'bg-gradient-to-br from-slate-900/85 via-slate-950/85 to-slate-900/85',
        'hover:-translate-y-0.5',
        STATUS_GLOW[data.status],
        data.status === 'running' && 'runtime-node-pulse',
      )}
      style={{ width: NODE_W, minHeight: NODE_H }}
      data-testid={`runtime-node-${data.id}`}
      data-status={data.status}
    >
      {/* Neon rim — gradient stroke implemented as a translucent
          inset border + a coloured glow halo defined in STATUS_GLOW. */}
      <span
        aria-hidden
        className={cn(
          'inset-0 pointer-events-none absolute rounded-2xl bg-gradient-to-br opacity-90',
          STATUS_ACCENT[data.status],
        )}
        style={{
          mask: 'linear-gradient(#000, #000) content-box, linear-gradient(#000, #000)',
          maskComposite: 'exclude',
          WebkitMask:
            'linear-gradient(#000, #000) content-box, linear-gradient(#000, #000)',
          WebkitMaskComposite: 'xor',
          padding: 1,
        }}
      />

      {/* Faint scanline texture for that "agent runtime" terminal feel. */}
      <span
        aria-hidden
        className="inset-0 pointer-events-none absolute rounded-2xl opacity-[0.07]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(148,163,184,0.6) 0 1px, transparent 1px 3px)',
        }}
      />

      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !rounded-full !border !border-cyan-300/60 !bg-slate-900 !shadow-[0_0_10px_rgba(34,211,238,0.6)]"
      />

      <div className="relative flex h-full flex-col gap-2 px-3.5 py-3">
        <div className="flex items-center gap-2.5">
          <div
            className={cn(
              'flex size-8 shrink-0 items-center justify-center rounded-xl border border-white/5 bg-slate-900/80',
              'shadow-[inset_0_0_12px_rgba(34,211,238,0.18)]',
            )}
          >
            <BlockIcon
              size="sm"
              type={data.type as BlockEnum}
              className="shrink-0"
            />
          </div>
          <div className="min-w-0 grow">
            <div className="truncate system-sm-semibold text-slate-50">
              {data.title || data.id}
            </div>
            <div className="truncate system-2xs-regular tracking-wider text-slate-400 uppercase">
              {data.type}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 rounded-full border border-white/5 bg-slate-950/60 px-2 py-0.5">
            <StatusBadge status={data.status} />
            <span
              className={cn(
                'system-2xs-medium tracking-wider uppercase',
                STATUS_TEXT[data.status],
              )}
            >
              {STATUS_LABEL[data.status]}
            </span>
          </div>
        </div>

        {summary && (
          <div
            className={cn(
              'line-clamp-2 system-xs-regular',
              data.error ? 'text-rose-300' : 'text-slate-300',
            )}
          >
            {summary}
          </div>
        )}

        <NodeMediaPreview outputs={data.outputs} />

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

        {showHumanInputCta && (
          <div className="mt-auto">
            <button
              type="button"
              onClick={() => openHumanInputDrawer(data.id)}
              className={cn(
                'group/cta relative flex w-full items-center justify-center gap-1.5 rounded-lg',
                'border border-amber-400/40 bg-gradient-to-r from-amber-500/15 via-orange-500/15 to-amber-500/15',
                'px-3 py-2 system-xs-semibold tracking-wide text-amber-200',
                'shadow-[0_0_18px_-6px_rgba(245,158,11,0.6)]',
                'transition hover:border-amber-300/70 hover:from-amber-500/25 hover:to-amber-500/25',
              )}
              data-testid={`runtime-human-input-cta-${data.id}`}
            >
              <span className="size-1.5 animate-pulse rounded-full bg-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.9)]" />
              等待你的输入 →
            </button>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !rounded-full !border !border-cyan-300/60 !bg-slate-900 !shadow-[0_0_10px_rgba(34,211,238,0.6)]"
      />

      <style jsx>
        {`
          :global(.runtime-node-pulse) {
            animation: runtimeNodePulse 1.6s ease-in-out infinite;
          }
          @keyframes runtimeNodePulse {
            0%,
            100% {
              box-shadow:
                0 0 0 1px rgba(34, 211, 238, 0.45),
                0 18px 55px -15px rgba(34, 211, 238, 0.55);
            }
            50% {
              box-shadow:
                0 0 0 1px rgba(99, 102, 241, 0.55),
                0 22px 65px -10px rgba(99, 102, 241, 0.7);
            }
          }
        `}
      </style>
    </div>
  )
}

export default RuntimeNodeComponent
