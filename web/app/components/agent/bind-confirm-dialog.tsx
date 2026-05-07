'use client'

import * as React from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/app/components/base/ui/toast'
import { useAgentPreview, useConfirmBind } from '@/service/use-agent'

type BindConfirmDialogProps = {
  /** Invitation code from URL or sessionStorage. ``null`` means hidden. */
  code: string | null
  /** Whether the customer already has a binding (drives copy + flow). */
  alreadyBound?: boolean
  /** Called when the user confirms / cancels / dismisses. */
  onClose: () => void
  /** Called after a successful bind. Frontend uses this to invalidate caches. */
  onSuccess?: () => void
}

const BindConfirmDialog = ({
  code,
  alreadyBound = false,
  onClose,
  onSuccess,
}: BindConfirmDialogProps) => {
  const { t } = useTranslation()
  const preview = useAgentPreview(code)
  const confirm = useConfirmBind()

  if (!code)
    return null

  const handleConfirm = () => {
    if (!code)
      return
    if (alreadyBound) {
      // Rebind flow needs from_agent_id + to_agent_id; the customer
      // doesn't have those handy, so this dialog asks the user to
      // reach out via support for now. The full rebind UI lives on
      // a separate ticket.
      toast.info(t('agent:bind.dialog.success.rebind'))
      onClose()
      return
    }
    confirm.mutate(code, {
      onSuccess: () => {
        toast.success(t('agent:bind.dialog.success.bind'))
        onSuccess?.()
        onClose()
      },
      onError: (err) => {
        const message = String(err?.message ?? '')
        if (message.includes('already_bound'))
          toast.warning(t('agent:bind.dialog.error.duplicate'))
        else toast.error(message || t('agent:bind.dialog.error.invalid'))
      },
    })
  }

  const agent = preview.data
  const region = agent?.region_province
    ? t('agent:bind.dialog.detail.region', {
        province: agent.region_province ?? '',
        city: agent.region_city ?? '',
      })
    : null

  return (
    <div className="inset-0 fixed z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg bg-background-default p-6 shadow-lg">
        <h2 className="text-lg font-semibold text-text-primary">
          {alreadyBound
            ? t('agent:bind.dialog.title.rebind')
            : t('agent:bind.dialog.title.confirm')}
        </h2>

        {preview.isLoading && (
          <p className="mt-4 text-sm text-text-tertiary">Loading...</p>
        )}

        {preview.error && (
          <p className="text-state-destructive-text mt-4 text-sm">
            {t('agent:bind.dialog.error.invalid')}
          </p>
        )}

        {agent && (
          <div className="mt-4 flex flex-col gap-2">
            <p className="text-sm text-text-secondary">
              {alreadyBound
                ? t('agent:bind.dialog.intro.rebind', { name: agent.name })
                : t('agent:bind.dialog.intro.confirm', { name: agent.name })}
            </p>
            {agent.level && (
              <span className="text-xs text-text-tertiary">
                {t(`agent:bind.dialog.detail.level.${agent.level}`)}
                {region ? ` · ${region}` : ''}
              </span>
            )}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-components-button-secondary-border px-4 py-2 text-sm text-text-secondary hover:bg-state-base-hover"
          >
            {t('agent:bind.dialog.cancel')}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!agent || confirm.isPending}
            className="rounded-md bg-components-button-primary-bg px-4 py-2 text-sm font-medium text-components-button-primary-text shadow-xs disabled:opacity-50"
          >
            {alreadyBound
              ? t('agent:bind.dialog.confirmRebind')
              : t('agent:bind.dialog.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}

export default BindConfirmDialog
