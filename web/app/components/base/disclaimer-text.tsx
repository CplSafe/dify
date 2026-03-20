import type { ReactNode } from 'react'
import { memo, useMemo } from 'react'
import { cn } from '@/utils/classnames'

type DisclaimerTextProps = {
  content?: string | null
  className?: string
}

const PHONE_PATTERN = /\+?\d[\d\s\-()]{5,}\d/g

const normalizeTelHref = (value: string) => {
  const trimmed = value.trim()
  const normalized = trimmed.replace(/[^\d+]/g, '')
  const digitsOnly = normalized.replace(/\D/g, '')

  if (digitsOnly.length < 7)
    return null

  return normalized.startsWith('+') ? normalized : digitsOnly
}

const DisclaimerText = ({
  content,
  className,
}: DisclaimerTextProps) => {
  const nodes = useMemo(() => {
    if (!content)
      return []

    const parts: ReactNode[] = []
    let lastIndex = 0

    for (const match of content.matchAll(PHONE_PATTERN)) {
      const matchText = match[0]
      const matchIndex = match.index ?? 0

      if (matchIndex > lastIndex)
        parts.push(content.slice(lastIndex, matchIndex))

      const telHref = normalizeTelHref(matchText)
      if (!telHref) {
        parts.push(matchText)
      }
      else {
        parts.push(
          <a
            key={`${matchText}-${matchIndex}`}
            href={`tel:${telHref}`}
            className="font-medium text-text-accent underline underline-offset-2 hover:text-text-accent-secondary"
          >
            {matchText}
          </a>,
        )
      }

      lastIndex = matchIndex + matchText.length
    }

    if (lastIndex < content.length)
      parts.push(content.slice(lastIndex))

    return parts
  }, [content])

  if (!content)
    return null

  return (
    <div className={cn('whitespace-pre-wrap break-words', className)}>
      {nodes}
    </div>
  )
}

export default memo(DisclaimerText)
