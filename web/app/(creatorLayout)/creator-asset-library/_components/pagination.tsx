'use client'

import { useTranslation } from 'react-i18next'

type PaginationProps = {
  page: number
  total: number
  limit: number
  hasMore: boolean
  onChange: (page: number) => void
}

export default function Pagination({
  page,
  total,
  limit,
  hasMore,
  onChange,
}: PaginationProps) {
  const { t } = useTranslation('assetLibrary')

  if (total <= limit)
    return null

  const totalPages = Math.max(1, Math.ceil(total / limit))

  return (
    <div className="mt-4 flex items-center justify-end gap-2 text-sm">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        className="h-8 rounded-md border border-divider-subtle px-3 text-text-secondary disabled:opacity-50"
      >
        {t('pagination.previous')}
      </button>
      <span className="min-w-24 text-center text-text-tertiary">
        {t('pagination.page', { current: page, total: totalPages })}
      </span>
      <button
        type="button"
        disabled={!hasMore}
        onClick={() => onChange(page + 1)}
        className="h-8 rounded-md border border-divider-subtle px-3 text-text-secondary disabled:opacity-50"
      >
        {t('pagination.next')}
      </button>
    </div>
  )
}
