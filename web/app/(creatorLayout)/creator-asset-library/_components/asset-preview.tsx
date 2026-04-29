'use client'

import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { useTranslation } from 'react-i18next'
import { toast } from '@/app/components/base/ui/toast'

type AssetPreviewProps = {
  asset: AssetLibraryItem
}

export default function AssetPreview({ asset }: AssetPreviewProps) {
  const { t } = useTranslation('assetLibrary')
  const url = asset.signed_url ?? ''

  if (asset.asset_type === 'image') {
    return (
      <img
        src={url}
        alt={asset.name}
        className="max-h-full max-w-full object-contain"
      />
    )
  }

  if (asset.asset_type === 'video') {
    return (
      <video
        controls
        src={url}
        data-testid="asset-preview-video"
        className="max-h-full max-w-full"
      />
    )
  }

  if (asset.asset_type === 'audio') {
    return (
      <audio
        controls
        src={url}
        data-testid="asset-preview-audio"
        className="w-full"
      />
    )
  }

  const copy = async () => {
    await navigator.clipboard.writeText(asset.content ?? '')
    toast.success(t('detail.copiedToast'))
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <pre className="flex-1 overflow-auto rounded-md bg-background-section p-3 system-sm-regular whitespace-pre-wrap text-text-primary">
        {asset.content ?? ''}
      </pre>
      <button
        type="button"
        onClick={copy}
        className="self-end rounded-md border border-divider-subtle px-3 py-1.5 system-sm-medium text-text-secondary hover:bg-state-base-hover hover:text-text-primary"
      >
        {t('detail.copyContent')}
      </button>
    </div>
  )
}
