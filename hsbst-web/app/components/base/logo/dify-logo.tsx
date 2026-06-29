'use client'
import type { FC } from 'react'
import { cn } from '@/utils/classnames'

export type LogoStyle = 'default' | 'monochromeWhite'

export const logoPathMap: Record<LogoStyle, string> = {
  default: '/logo/logo.svg',
  monochromeWhite: '/logo/logo-monochrome-white.svg',
}

export type LogoSize = 'large' | 'medium' | 'small'

export const logoSizeMap: Record<LogoSize, string> = {
  large: 'w-16 h-7',
  medium: 'w-12 h-[22px]',
  small: 'w-9 h-4',
}

type DifyLogoProps = {
  style?: LogoStyle
  size?: LogoSize
  className?: string
}

const DifyLogo: FC<DifyLogoProps> = ({
  style = 'default',
  size = 'medium',
  className,
}) => {
  const isWhite = style === 'monochromeWhite'
  const markSize = size === 'large' ? 'h-7 w-7 text-sm' : size === 'small' ? 'h-5 w-5 text-[11px]' : 'h-6 w-6 text-xs'
  const textSize = size === 'large' ? 'text-base' : size === 'small' ? 'text-xs' : 'text-sm'

  return (
    <span
      className={cn('inline-flex items-center gap-2 whitespace-nowrap', className)}
      aria-label="赫山百事通"
    >
      <span className={cn('inline-flex shrink-0 items-center justify-center rounded-lg bg-primary-600 font-semibold text-white', markSize)}>
        赫
      </span>
      <span className={cn('font-semibold', textSize, isWhite ? 'text-white' : 'text-text-primary')}>
        赫山百事通
      </span>
    </span>
  )
}

export default DifyLogo
