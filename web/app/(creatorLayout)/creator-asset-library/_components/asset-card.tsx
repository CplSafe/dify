import type { AssetLibraryItem } from '@/contract/console/asset-library'

type AssetCardProps = {
  item: AssetLibraryItem
  onSelect: (id: string) => void
}

export default function AssetCard({ item, onSelect }: AssetCardProps) {
  const isVideo = item.asset_type === 'video'
  const previewUrl = isVideo
    ? item.cover_url ?? item.signed_url
    : item.signed_url

  return (
    <button
      type="button"
      aria-label={item.name}
      onClick={() => onSelect(item.id)}
      className="group relative aspect-4/3 overflow-hidden rounded-lg border border-divider-subtle bg-background-section text-left"
    >
      {previewUrl
        ? (
            <img
              src={previewUrl}
              alt={item.name}
              className="h-full w-full object-cover"
            />
          )
        : (
            <div
              data-testid="asset-placeholder"
              className="flex h-full w-full items-center justify-center text-text-tertiary"
            >
              <span aria-hidden className="i-ri-image-2-line h-10 w-10" />
            </div>
          )}
      {isVideo && (
        <>
          <span
            aria-hidden
            className="inset-0 absolute m-auto i-ri-play-circle-line h-12 w-12 text-white opacity-0 transition-opacity group-hover:opacity-90"
          />
          {item.duration != null && (
            <span className="absolute right-2 bottom-2 rounded bg-black/70 px-1.5 py-0.5 text-[11px] text-white">
              {item.duration.toFixed(1)}
              s
            </span>
          )}
        </>
      )}
      <div className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent p-2 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
        {item.name}
      </div>
    </button>
  )
}
