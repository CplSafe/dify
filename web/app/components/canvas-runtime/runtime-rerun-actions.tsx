'use client'

import type { FC } from 'react'
import type { RuntimeNode } from './runtime-store'
import type { RerunOverrideApi } from '@/app/components/workflow/run/rerun-override-modal'
import type { ChatflowRerunKind } from '@/service/debug'
import { useCallback, useMemo, useState } from 'react'
import RerunOverrideModal from '@/app/components/workflow/run/rerun-override-modal'
import {
  deleteCanvasRerunOverride,
  dispatchCanvasRerun,
  prepareCanvasRerun,
  upsertCanvasRerunOverride,
} from '@/service/canvas-runtime'
import { useRuntimeStore } from './runtime-store'

type RuntimeRerunActionsProps = {
  /** installed_app_id (URL slug for installed-apps endpoints). */
  installedAppId: string
  node: RuntimeNode
  allowInput: boolean
  allowOutput: boolean
}

/**
 * Inline 重跑 trigger painted onto a *succeeded* node, mirroring the
 * pause-state CTAs but routed to CR10's terminated-rerun backend.
 *
 * Why a separate component: the pause version reuses the canvas's
 * synchronous `clearPause` reducer, which doesn't apply here — the run
 * already terminated, so there's no pause marker to drop. Instead we
 * just enqueue the rerun and let the SSE topic deliver fresh
 * node_started / node_finished events that overwrite the prior status.
 */
const RuntimeRerunActions: FC<RuntimeRerunActionsProps> = ({
  installedAppId,
  node,
  allowInput,
  allowOutput,
}) => {
  const messageId = useRuntimeStore(s => s.messageId)
  const [editKind, setEditKind] = useState<ChatflowRerunKind | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Inject installed-apps scoped endpoints into the shared modal so it
  // can target the creator routes instead of console-admin ones.
  const api = useMemo<RerunOverrideApi | undefined>(() => {
    if (!messageId)
      return undefined
    return {
      upsertOverride: ({ nodeId, kind, data }) =>
        upsertCanvasRerunOverride({
          installedAppId,
          messageId,
          nodeId,
          kind,
          data,
        }),
      prepare: ({ nodeId, kind }) =>
        prepareCanvasRerun({ installedAppId, messageId, nodeId, kind }),
      dispatch: ({ nodeId, kind }) =>
        dispatchCanvasRerun({ installedAppId, messageId, nodeId, kind }),
      deleteOverride: ({ nodeId, kind }) =>
        deleteCanvasRerunOverride({ installedAppId, messageId, nodeId, kind }),
    }
  }, [installedAppId, messageId])

  const handleConfirmed = useCallback(() => {
    setError(null)
  }, [])

  const initialData = (
    editKind === 'input' ? (node.inputs ?? {}) : (node.outputs ?? {})
  ) as Record<string, unknown>

  if (!allowInput && !allowOutput)
    return null

  return (
    <div className="mt-2 border-t border-divider-subtle pt-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="system-2xs-medium-uppercase text-text-tertiary">
          重跑
        </span>
        {allowInput && (
          <button
            type="button"
            onClick={() => setEditKind('input')}
            disabled={!messageId}
            className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            data-testid={`runtime-rerun-input-${node.id}`}
          >
            编辑输入并重跑
          </button>
        )}
        {allowOutput && (
          <button
            type="button"
            onClick={() => setEditKind('output')}
            disabled={!messageId}
            className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            data-testid={`runtime-rerun-output-${node.id}`}
          >
            编辑输出并重跑
          </button>
        )}
      </div>
      {error && (
        <div className="mt-1 system-xs-regular text-text-destructive">
          {error}
        </div>
      )}
      {editKind && messageId && api && (
        <RerunOverrideModal
          open={editKind !== null}
          appId={installedAppId}
          messageId={messageId}
          nodeId={node.id}
          nodeTitle={node.title || node.id}
          kind={editKind}
          initialData={initialData}
          onClose={() => setEditKind(null)}
          onConfirmed={handleConfirmed}
          api={api}
        />
      )}
    </div>
  )
}

export default RuntimeRerunActions
