'use client'

import { useTranslation } from 'react-i18next'
import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogCancelButton,
  AlertDialogConfirmButton,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/app/components/base/ui/alert-dialog'

type DeleteConfirmDialogProps = {
  open: boolean
  name: string
  onCancel: () => void
  onConfirm: () => void
}

export default function DeleteConfirmDialog({
  open,
  name,
  onCancel,
  onConfirm,
}: DeleteConfirmDialogProps) {
  const { t } = useTranslation('assetLibrary')

  return (
    <AlertDialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen)
          onCancel()
      }}
    >
      <AlertDialogContent>
        <div className="flex flex-col gap-2 px-6 pt-6 pb-4">
          <AlertDialogTitle className="title-2xl-semi-bold text-text-primary">
            {t('detail.deleteConfirmTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription className="system-md-regular text-text-tertiary">
            {t('detail.deleteConfirmBody', { name })}
          </AlertDialogDescription>
        </div>
        <AlertDialogActions>
          <AlertDialogCancelButton>
            {t('detail.deleteCancel')}
          </AlertDialogCancelButton>
          <AlertDialogConfirmButton onClick={onConfirm}>
            {t('detail.deleteConfirm')}
          </AlertDialogConfirmButton>
        </AlertDialogActions>
      </AlertDialogContent>
    </AlertDialog>
  )
}
