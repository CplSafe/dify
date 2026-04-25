'use client'

import type { FC } from 'react'
import { useCallback, useEffect, useState } from 'react'
import Button from '@/app/components/base/button'
import {
  Dialog,
  DialogClose,
  DialogCloseButton,
  DialogContent,
  DialogTitle,
} from '@/app/components/base/ui/dialog'
import { createUserCanvas } from '@/service/user-canvases'

type SaveCanvasDialogProps = {
  open: boolean
  appId: string
  sourceRunId: string | null
  onClose: () => void
  onSaved?: (canvasId: string) => void
}

const SaveCanvasDialog: FC<SaveCanvasDialogProps> = ({
  open,
  appId,
  sourceRunId,
  onClose,
  onSaved,
}) => {
  const [title, setTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset form whenever the dialog reopens. The set-state-in-effect
  // warning doesn't apply: this is a single-shot reset, not a derived
  // mirror of incoming props.
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react/set-state-in-effect
      setTitle('')
      // eslint-disable-next-line react/set-state-in-effect
      setError(null)
      // eslint-disable-next-line react/set-state-in-effect
      setSubmitting(false)
    }
  }, [open])

  const canSubmit = !!sourceRunId && title.trim().length > 0 && !submitting

  const handleSubmit = useCallback(async () => {
    if (!sourceRunId) {
      setError('当前没有可保存的运行，请先在画布上完成一次运行')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const row = await createUserCanvas({
        app_id: appId,
        title: title.trim(),
        source_run_id: sourceRunId,
      })
      onSaved?.(row.id)
      onClose()
    }
    catch (e: unknown) {
      setError(e instanceof Error ? e.message : '保存失败，请重试')
    }
    finally {
      setSubmitting(false)
    }
  }, [appId, onClose, onSaved, sourceRunId, title])

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v)
          onClose()
      }}
    >
      <DialogContent className="w-[480px]">
        <DialogTitle className="mb-2 title-2xl-semi-bold text-text-primary">
          保存为画布
        </DialogTitle>
        <p className="mb-4 system-xs-regular text-text-tertiary">
          画布会保存这次运行的所有节点输入与输出，下次打开可重现并继续编辑。
        </p>
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="给这次画布起个名字"
          maxLength={200}
          className="border-components-input-border bg-components-input-bg mb-3 w-full rounded-lg border px-3 py-2 system-md-regular text-text-primary outline-hidden focus:border-components-input-border-hover"
        />
        {!sourceRunId && (
          <div className="mb-3 system-xs-regular text-text-tertiary">
            尚未运行任何工作流，先在底部输入框发送一次再保存。
          </div>
        )}
        {error && (
          <div className="mb-3 rounded-md border border-state-destructive-border bg-state-destructive-hover px-3 py-2 system-xs-regular text-text-destructive">
            {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-2">
          <DialogClose render={<Button variant="secondary">取消</Button>} />
          <Button
            variant="primary"
            loading={submitting}
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            保存
          </Button>
        </div>
        <DialogCloseButton />
      </DialogContent>
    </Dialog>
  )
}

export default SaveCanvasDialog
