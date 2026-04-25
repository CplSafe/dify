'use client'

import type { FC } from 'react'
import type { PausedNodeKinds, RuntimeNode } from './runtime-store'
import type { ChatflowRerunKind } from '@/service/debug'
import { useCallback, useState } from 'react'
import RerunOverrideModal from '@/app/components/workflow/run/rerun-override-modal'
import { resumeChatflowFromNode } from '@/service/debug'
import { useRuntimeStore } from './runtime-store'

type RuntimePauseActionsProps = {
  appId: string
  node: RuntimeNode
  kinds: PausedNodeKinds
}

/**
 * Inline "继续 / 编辑后继续" CTA painted onto a paused node.
 *
 * - 继续: POST resume-from/<node_id> — celery picks up the saved pause
 *   state and the chatflow continues with the original outputs.
 * - 编辑输入并重跑 / 编辑输出并重跑: open the M6 RerunOverrideModal,
 *   which persists the override via M2 then dispatches resume itself.
 *
 * Human-input pauses are NOT handled here — the existing form flow
 * unblocks those (the kinds.source === 'human_input' guard upstream
 * keeps this component out of those nodes' DOM).
 */
const RuntimePauseActions: FC<RuntimePauseActionsProps> = ({
  appId,
  node,
  kinds,
}) => {
  const messageId = useRuntimeStore(s => s.messageId)
  const clearPause = useRuntimeStore(s => s.clearPause)

  const [editKind, setEditKind] = useState<ChatflowRerunKind | null>(null)
  const [resuming, setResuming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleResume = useCallback(async () => {
    if (!messageId)
      return
    setError(null)
    setResuming(true)
    try {
      // FIX10: explicitly send kind='output' so prepare() picks the
      // downstream node as start_node_id. The user-facing "继续" means
      // "this paused node's output is fine, go on to the next node";
      // 'input' would re-anchor on the paused node itself, which the
      // resume path can't actually replay.
      await resumeChatflowFromNode({
        appId,
        messageId,
        nodeId: node.id,
        kind: 'output',
      })
      // Optimistically clear the pause marker; the SSE workflow_finished
      // (or the next node_started) will reconcile the real state.
      clearPause(node.id)
    }
    catch (e: unknown) {
      setError(e instanceof Error ? e.message : '继续失败，请重试')
    }
    finally {
      setResuming(false)
    }
  }, [appId, clearPause, messageId, node.id])

  const handleEditConfirmed = useCallback(() => {
    // The modal already called dispatch (which is the same celery
    // resume path). Clear the pause locally; SSE will fix things up.
    clearPause(node.id)
  }, [clearPause, node.id])

  const initialData = (
    editKind === 'input' ? (node.inputs ?? {}) : (node.outputs ?? {})
  ) as Record<string, unknown>

  return (
    <div className="mt-2 border-t border-divider-subtle pt-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="system-2xs-medium-uppercase text-text-tertiary">
          已暂停
        </span>
        <button
          type="button"
          onClick={handleResume}
          disabled={resuming || !messageId}
          className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          data-testid={`runtime-pause-resume-${node.id}`}
        >
          {resuming ? '继续中…' : '继续'}
        </button>
        {/*
          FIX10: input-kind edits cannot apply to a paused-resume path.
          The engine's pause point sits *after* the node finished, so a
          resume continues on the next node and never re-feeds the
          edited input back into the paused node. The button stays
          rendered (so users discover the capability) but disabled,
          with a tooltip-style title explaining the constraint.
        */}
        {kinds.allowInput && (
          <button
            type="button"
            disabled
            title="暂停状态下无法编辑输入：当前节点已运行结束，恢复时会从下一节点继续。请改用『编辑输出并继续』。"
            className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            data-testid={`runtime-pause-edit-input-${node.id}`}
          >
            编辑输入并继续
          </button>
        )}
        {kinds.allowOutput && (
          <button
            type="button"
            onClick={() => setEditKind('output')}
            disabled={resuming || !messageId}
            className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
            data-testid={`runtime-pause-edit-output-${node.id}`}
          >
            编辑输出并继续
          </button>
        )}
      </div>
      {error && (
        <div className="mt-1 system-xs-regular text-text-destructive">
          {error}
        </div>
      )}
      {editKind && messageId && (
        <RerunOverrideModal
          open={editKind !== null}
          appId={appId}
          messageId={messageId}
          nodeId={node.id}
          nodeTitle={node.title || node.id}
          kind={editKind}
          initialData={initialData}
          onClose={() => setEditKind(null)}
          onConfirmed={handleEditConfirmed}
        />
      )}
    </div>
  )
}

export default RuntimePauseActions
