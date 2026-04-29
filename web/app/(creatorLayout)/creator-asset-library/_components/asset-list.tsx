'use client'

import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { useTranslation } from 'react-i18next'
import AssetRow from './asset-row'

const SKELETON_KEYS = ['one', 'two', 'three', 'four', 'five']

type AssetListProps = {
  items: AssetLibraryItem[]
  loading: boolean
  onSelect: (id: string) => void
}

export default function AssetList({
  items,
  loading,
  onSelect,
}: AssetListProps) {
  const { t } = useTranslation('assetLibrary')

  if (loading) {
    return (
      <div className="flex flex-col gap-1">
        {SKELETON_KEYS.map(key => (
          <div
            key={key}
            data-testid="asset-skeleton-row"
            className="h-12 animate-pulse rounded-md bg-background-section"
          />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="py-16 text-center text-text-tertiary">
        {t('empty.all')}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      {items.map(item => (
        <AssetRow key={item.id} item={item} onSelect={onSelect} />
      ))}
    </div>
  )
}
