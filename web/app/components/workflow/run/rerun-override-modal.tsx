'use client'

import type { FC } from 'react'
import type { ChatflowRerunKind } from '@/service/debug'
import { useCallback, useMemo, useState } from 'react'
import Button from '@/app/components/base/button'
import {
  Dialog,
  DialogClose,
  DialogCloseButton,
  DialogContent,
  DialogTitle,
} from '@/app/components/base/ui/dialog'
import CodeEditor from '@/app/components/workflow/nodes/_base/components/editor/code-editor'
import { CodeLanguage } from '@/app/components/workflow/nodes/code/types'
import {
  deleteChatflowRerunOverride,
  prepareChatflowRerun,
  upsertChatflowRerunOverride,
} from '@/service/debug'

type RerunOverrideModalProps = {
  open: boolean
  appId: string
  messageId: string
  nodeId: string
  nodeTitle: string
  kind: ChatflowRerunKind
  initialData: Record<string, unknown>
  onClose: () => void
  // Fired once the override has been persisted AND the rerun plan has been
  // validated. M7 will use this to hand off to the streaming dispatcher.
  // M6 just closes the modal.
  onConfirmed?: (payload: {
    nodeId: string
    kind: ChatflowRerunKind
    data: Record<string, unknown>
  }) => void
}

const stringifyForEditor = (value: Record<string, unknown>) => {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  }
  catch {
    return '{}'
  }
}

/**
 * Modal for editing a chatflow node's input or output override before
 * triggering a rerun.
 *
 * Flow:
 *   1. Validate JSON locally.
 *   2. PUT override (M2) — server enforces `allow_user_edit_*` and loop rules.
 *   3. POST rerun-from (M1) — server returns the rewind plan and surfaces
 *      blocking errors (e.g. node sits inside a loop) before the user
 *      thinks the rerun has started.
 *   4. Hand off to onConfirmed (M7 will dispatch the actual streaming run;
 *      M6 just closes).
 *
 * "Reset" deletes the override for the given (node, kind) so the next
 * rerun re-uses the original execution data.
 */
const RerunOverrideModal: FC<RerunOverrideModalProps> = ({
  open,
  appId,
  messageId,
  nodeId,
  nodeTitle,
  kind,
  initialData,
  onClose,
  onConfirmed,
}) => {
  const initialText = useMemo(
    () => stringifyForEditor(initialData),
    [initialData],
  )
  const [text, setText] = useState(initialText)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [resetting, setResetting] = useState(false)

  // Reset local state every time the modal is reopened on a different node.
  const dialogKey = `${nodeId}:${kind}:${open ? 'open' : 'closed'}`

  const handleConfirm = useCallback(async () => {
    setError(null)
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(text)
    }
    catch (e: unknown) {
      setError(
        e instanceof Error ? `JSON 解析失败：${e.message}` : 'JSON 解析失败',
      )
      return
    }
    if (
      parsed === null
      || typeof parsed !== 'object'
      || Array.isArray(parsed)
    ) {
      setError('JSON 顶层必须是一个对象')
      return
    }

    setSubmitting(true)
    try {
      await upsertChatflowRerunOverride({
        appId,
        messageId,
        nodeId,
        kind,
        data: parsed,
      })
      // Validate the resulting rerun plan synchronously so the user sees
      // any "node is inside a loop" / permission errors right here instead
      // of after closing the modal.
      await prepareChatflowRerun({ appId, messageId, nodeId, kind })
      onConfirmed?.({ nodeId, kind, data: parsed })
      onClose()
    }
    catch (e: unknown) {
      setError(e instanceof Error ? e.message : '保存失败，请重试')
    }
    finally {
      setSubmitting(false)
    }
  }, [appId, messageId, nodeId, kind, text, onConfirmed, onClose])

  const handleReset = useCallback(async () => {
    setError(null)
    setResetting(true)
    try {
      await deleteChatflowRerunOverride({ appId, messageId, nodeId, kind })
      setText(initialText)
    }
    catch (e: unknown) {
      setError(e instanceof Error ? e.message : '重置失败，请重试')
    }
    finally {
      setResetting(false)
    }
  }, [appId, messageId, nodeId, kind, initialText])

  const title
    = kind === 'input'
      ? `编辑输入并重跑 · ${nodeTitle}`
      : `编辑输出并重跑 · ${nodeTitle}`

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v)
          onClose()
      }}
    >
      <DialogContent
        key={dialogKey}
        className="w-[640px] max-w-[calc(100vw-2rem)]"
      >
        <DialogTitle className="mb-2 title-2xl-semi-bold text-text-primary">
          {title}
        </DialogTitle>
        <p className="mb-4 system-xs-regular text-text-tertiary">
          编辑后将从该节点
          {kind === 'input' ? '' : '的下游节点'}
          重新运行；上游节点的输出会被复用，不会再次计费。
        </p>
        <div className="mb-3 rounded-lg border border-components-panel-border">
          <CodeEditor
            value={text}
            onChange={setText}
            language={CodeLanguage.json}
            title={kind === 'input' ? '输入 JSON' : '输出 JSON'}
            height={320}
          />
        </div>
        {error && (
          <div className="mb-3 rounded-md border border-state-destructive-border bg-state-destructive-hover px-3 py-2 system-xs-regular text-text-destructive">
            {error}
          </div>
        )}
        <div className="flex items-center justify-between gap-2">
          <Button
            variant="ghost"
            disabled={resetting || submitting}
            onClick={handleReset}
          >
            {resetting ? '重置中…' : '重置为原始值'}
          </Button>
          <div className="flex items-center gap-2">
            <DialogClose render={<Button variant="secondary">取消</Button>} />
            <Button
              variant="primary"
              loading={submitting}
              disabled={submitting || resetting}
              onClick={handleConfirm}
            >
              保存并准备重跑
            </Button>
          </div>
        </div>
        <DialogCloseButton />
      </DialogContent>
    </Dialog>
  )
}

export default RerunOverrideModal
