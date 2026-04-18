'use client'

import type { SocialPublishAccount } from '@/types/social-publish'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/app/components/base/ui/dialog'

type Props = {
  open: boolean
  account: SocialPublishAccount | null
  loading: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function DeleteAccountConfirm({ open, account, loading, onCancel, onConfirm }: Props) {
  const { t } = useTranslation('socialPublish')

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o)
          onCancel()
      }}
    >
      <DialogContent className="w-[400px]">
        <DialogTitle className="text-base font-semibold text-text-primary">
          {t('accountList.deleteConfirm.title')}
        </DialogTitle>
        <DialogDescription className="mt-2 text-sm text-text-tertiary">
          {t('accountList.deleteConfirm.description')}
          {account?.display_name && (
            <span className="mt-1 block font-medium text-text-secondary">
              {account.display_name}
            </span>
          )}
        </DialogDescription>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            {t('accountList.deleteConfirm.cancel')}
          </Button>
          <Button variant="primary" destructive onClick={onConfirm} loading={loading}>
            {t('accountList.deleteConfirm.confirm')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
