'use client'

import type { AssetType } from '@/contract/console/asset-library'
import { useTranslation } from 'react-i18next'
import { cn } from '@/utils/classnames'

export type TabValue = 'all' | AssetType

const TABS: TabValue[] = ['all', 'image', 'video', 'audio', 'prompt']

type AssetTabsProps = {
  value: TabValue
  onChange: (value: TabValue) => void
}

export default function AssetTabs({ value, onChange }: AssetTabsProps) {
  const { t } = useTranslation('assetLibrary')

  return (
    <div
      role="tablist"
      className="flex items-center gap-1 border-b border-divider-subtle"
    >
      {TABS.map((tab) => {
        const active = value === tab

        return (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={active}
            data-active={active}
            onClick={() => onChange(tab)}
            className={cn(
              '-mb-px h-10 border-b-2 px-4 text-sm font-medium transition-colors',
              active
                ? 'border-primary-600 text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary',
            )}
          >
            {t(`tabs.${tab}`)}
          </button>
        )
      })}
    </div>
  )
}
