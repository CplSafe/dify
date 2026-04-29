import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { useTranslation } from 'react-i18next'

const PREVIEW_LIMIT = 50

const formatDuration = (seconds: number | null) => {
  if (seconds == null)
    return ''

  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60).toString().padStart(2, '0')

  return `${minutes}:${remainingSeconds}`
}

type AssetRowProps = {
  item: AssetLibraryItem
  onSelect: (id: string) => void
}

export default function AssetRow({ item, onSelect }: AssetRowProps) {
  const { t } = useTranslation('assetLibrary')
  const isPrompt = item.asset_type === 'prompt'
  const preview = item.content
    ? item.content.length > PREVIEW_LIMIT
      ? `${item.content.slice(0, PREVIEW_LIMIT)}...`
      : item.content
    : ''

  return (
    <button
      type="button"
      onClick={() => onSelect(item.id)}
      className="grid w-full grid-cols-[24px_1fr_120px_120px_160px_120px] items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm hover:bg-background-section"
    >
      <span
        aria-hidden
        className={isPrompt
          ? 'i-ri-file-text-line h-5 w-5 text-text-tertiary'
          : 'i-ri-music-line h-5 w-5 text-text-tertiary'}
      />
      <div className="min-w-0">
        <div className="truncate font-medium text-text-primary">{item.name}</div>
        {isPrompt && preview && (
          <div className="truncate text-xs text-text-tertiary">{preview}</div>
        )}
      </div>
      <div className="text-text-tertiary">{t(`tabs.${item.asset_type}`)}</div>
      <div className="text-text-tertiary">
        {!isPrompt && formatDuration(item.duration)}
      </div>
      <div className="flex min-w-0 flex-wrap gap-1">
        {item.tags.slice(0, 3).map(tag => (
          <span
            key={tag}
            className="rounded-full bg-background-section px-1.5 py-0.5 text-xs text-text-secondary"
          >
            {tag}
          </span>
        ))}
      </div>
      <div className="truncate text-text-tertiary">
        {item.created_by?.name ?? ''}
      </div>
    </button>
  )
}
