'use client'
import { usePathname } from 'next/navigation'
import { useTranslation } from 'react-i18next'
import { useLocale } from '@/context/i18n'
import { cn } from '@/utils/classnames'
import { getRelativeTime, isRelativeTimeSameOrAfter } from './utils'

type ExpirationTimeProps = {
  expirationTime: number
}

const ExpirationTime = ({
  expirationTime,
}: ExpirationTimeProps) => {
  const pathname = usePathname()
  const isCreatorMode = pathname?.startsWith('/creator')
  const { t } = useTranslation()
  const locale = useLocale()
  const relativeTime = getRelativeTime(expirationTime, locale)
  const isSameOrAfter = isRelativeTimeSameOrAfter(expirationTime)

  return (
    <div
      data-testid="expiration-time"
      className={cn(
        isCreatorMode
          ? 'mt-2 flex items-center gap-x-1 text-[13px] text-[#8B87A1]'
          : 'mt-1 flex items-center gap-x-1 text-text-tertiary system-xs-regular',
        !isSameOrAfter && 'text-text-warning',
      )}
    >
      {
        isSameOrAfter
          ? (
              <>
                <div className="i-ri-time-line size-3.5" />
                <span>{t('humanInput.expirationTimeNowOrFuture', { relativeTime, ns: 'share' })}</span>
              </>
            )
          : (
              <>
                <div className="i-ri-alert-fill size-3.5" />
                <span>{t('humanInput.expiredTip', { ns: 'share' })}</span>
              </>
            )
      }
    </div>
  )
}

export default ExpirationTime
