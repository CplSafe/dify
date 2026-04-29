'use client'

import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { useTranslation } from 'react-i18next'
import AssetCard from './asset-card'

const SKELETON_KEYS = ['one', 'two', 'three', 'four', 'five', 'six']

type AssetGridProps = {
  items: AssetLibraryItem[]
  loading: boolean
  onSelect: (id: string) => void
}

export default function AssetGrid({
  items,
  loading,
  onSelect,
}: AssetGridProps) {
  const { t } = useTranslation('assetLibrary')

  if (loading) {
    return (
      <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
        {SKELETON_KEYS.map(key => (
          <div
            key={key}
            data-testid="asset-skeleton"
            className="aspect-4/3 animate-pulse rounded-lg bg-background-section"
          />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-tertiary">
        <p>{t('empty.all')}</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
      {items.map(item => (
        <AssetCard key={item.id} item={item} onSelect={onSelect} />
      ))}
    </div>
  )
}
