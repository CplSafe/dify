'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

type AssetFilterBarProps = {
  keyword: string
  category: string | undefined
  tags: string[]
  onKeywordChange: (value: string) => void
  onCategoryChange: (value: string | undefined) => void
  onTagsChange: (value: string[]) => void
}

const DEBOUNCE_MS = 300

export default function AssetFilterBar({
  keyword,
  category,
  tags,
  onKeywordChange,
  onCategoryChange,
  onTagsChange,
}: AssetFilterBarProps) {
  const { t } = useTranslation('assetLibrary')
  const [localKeyword, setLocalKeyword] = useState(keyword)
  const [tagInput, setTagInput] = useState('')
  const previousKeywordRef = useRef(keyword)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  if (previousKeywordRef.current !== keyword) {
    previousKeywordRef.current = keyword
    if (localKeyword !== keyword)
      setLocalKeyword(keyword)
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current)
        clearTimeout(debounceRef.current)
    }
  }, [])

  const handleKeywordChange = (value: string) => {
    setLocalKeyword(value)

    if (debounceRef.current)
      clearTimeout(debounceRef.current)

    debounceRef.current = setTimeout(() => {
      onKeywordChange(value)
    }, DEBOUNCE_MS)
  }

  const addTag = () => {
    const value = tagInput.trim()

    if (!value || tags.includes(value)) {
      setTagInput('')
      return
    }

    onTagsChange([...tags, value])
    setTagInput('')
  }

  const removeTag = (tag: string) => {
    onTagsChange(tags.filter(value => value !== tag))
  }

  return (
    <div className="my-3 flex flex-wrap items-center gap-3">
      <input
        type="text"
        value={localKeyword}
        onChange={event => handleKeywordChange(event.target.value)}
        placeholder={t('filters.searchPlaceholder')}
        className="h-9 min-w-60 flex-1 rounded-md border border-divider-subtle px-3 text-sm focus:border-primary-600 focus:outline-none"
      />
      <input
        type="text"
        value={category ?? ''}
        onChange={event => onCategoryChange(event.target.value || undefined)}
        placeholder={t('filters.categoryPlaceholder')}
        className="h-9 w-40 rounded-md border border-divider-subtle px-3 text-sm focus:border-primary-600 focus:outline-none"
      />
      <div className="flex flex-wrap items-center gap-1.5">
        {tags.map(tag => (
          <span
            key={tag}
            className="inline-flex h-7 items-center gap-1 rounded-full bg-background-section px-2 text-xs text-text-secondary"
          >
            {tag}
            <button
              type="button"
              aria-label={t('filters.removeTag', { tag })}
              onClick={() => removeTag(tag)}
              className="flex h-4 w-4 items-center justify-center rounded-full text-text-tertiary hover:text-text-primary"
            >
              <span aria-hidden className="i-ri-close-line h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={tagInput}
          onChange={event => setTagInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              addTag()
            }
          }}
          placeholder={t('filters.tagsPlaceholder')}
          className="h-9 w-44 rounded-md border border-divider-subtle px-3 text-sm focus:border-primary-600 focus:outline-none"
        />
      </div>
    </div>
  )
}
