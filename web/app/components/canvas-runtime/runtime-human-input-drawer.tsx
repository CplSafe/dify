'use client'

import type { FC } from 'react'
import type { HumanInputFormData } from '@/types/workflow'
import { RiCloseLine } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import { UnsubmittedHumanInputContent } from '@/app/components/base/chat/chat/answer/human-input-content/unsubmitted'
import { submitHumanInputForm } from '@/service/workflow'
import { cn } from '@/utils/classnames'
import { useRuntimeStore } from './runtime-store'

type RuntimeHumanInputDrawerProps = {
  form: HumanInputFormData | null
  onClose: () => void
}

/**
 * Right-anchored side drawer that hosts the human-input form when a
 * canvas-runtime node pauses awaiting user input.
 *
 * Why a drawer (vs. inline card form):
 *   - form_content can be rich-text / multi-paragraph (the editor may
 *     embed instructions for the operator). Inflating the card to fit
 *     would break the uniform-grid layout we just introduced.
 *   - Field count varies (1..N inputs + N actions). A fixed-width side
 *     panel scrolls cleanly; the card stays the same height.
 *   - The user doesn't lose context — backdrop is translucent so the
 *     paused node stays visible behind, hinting "fill this to unblock".
 *
 * Reuses `<UnsubmittedHumanInputContent>` from the chat infrastructure,
 * the same component the chatflow preview uses, so form rendering &
 * validation behave identically across surfaces.
 */
const RuntimeHumanInputDrawer: FC<RuntimeHumanInputDrawerProps> = ({
  form,
  onClose,
}) => {
  const clearHumanInputForm = useRuntimeStore(s => s.clearHumanInputForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Close on Escape — matches dialog semantics users already know.
  useEffect(() => {
    if (!form)
      return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape')
        onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [form, onClose])

  const handleSubmit = useCallback(
    async (
      formToken: string,
      formData: { inputs: Record<string, string>, action: string },
    ) => {
      setError(null)
      setSubmitting(true)
      try {
        await submitHumanInputForm(formToken, formData)
        // Optimistically clear the form locally — the engine will fire
        // its own `human_input_form_filled` shortly which is a no-op
        // against the empty state.
        if (form)
          clearHumanInputForm(form.node_id)
        onClose()
      }
      catch (e: unknown) {
        setError(e instanceof Error ? e.message : '提交失败，请重试')
      }
      finally {
        setSubmitting(false)
      }
    },
    [clearHumanInputForm, form, onClose],
  )

  if (!form)
    return null

  return (
    <div className="inset-0 pointer-events-none fixed z-50">
      {/* Backdrop — translucent so the paused node stays visible. */}
      <div
        aria-hidden
        className={cn(
          'inset-0 pointer-events-auto absolute bg-slate-950/55 backdrop-blur-sm',
          'animate-in fade-in duration-200',
        )}
        onClick={onClose}
      />

      {/* Drawer panel — slides in from the right, fixed width. */}
      <aside
        role="dialog"
        aria-label={`${form.node_title || '人工输入'} · 等待输入`}
        className={cn(
          'pointer-events-auto absolute top-0 right-0 bottom-0 flex w-[420px] max-w-[90vw] flex-col',
          'border-l border-cyan-400/20 bg-slate-950/95 shadow-2xl shadow-cyan-500/15 backdrop-blur-xl',
          'animate-in slide-in-from-right duration-300',
        )}
      >
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-white/5 px-5 py-4">
          <span className="size-2 shrink-0 rounded-full bg-amber-400 shadow-[0_0_10px_rgba(245,158,11,0.8)]" />
          <div className="min-w-0 grow">
            <div className="system-2xs-medium tracking-wider text-amber-300 uppercase">
              等待你的输入
            </div>
            <div className="truncate system-md-semibold text-slate-50">
              {form.node_title || '人工输入'}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md p-1.5 text-slate-400 hover:bg-white/5 hover:text-slate-200 disabled:opacity-50"
            aria-label="关闭"
          >
            <RiCloseLine className="size-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <UnsubmittedHumanInputContent
            formData={form}
            onSubmit={handleSubmit}
          />
          {error && (
            <div className="mt-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 system-xs-regular text-rose-300">
              {error}
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

export default RuntimeHumanInputDrawer
