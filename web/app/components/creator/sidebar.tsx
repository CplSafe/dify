'use client'
/* eslint-disable tailwindcss/enforce-consistent-class-order -- TODO(wallet): preexisting issues tracked for a follow-up cleanup */

import { RiBroadcastLine, RiHome4Line, RiVideoLine } from '@remixicon/react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/app/components/base/ui/tooltip'
import { useGlobalPublicStore } from '@/context/global-public-context'
import Link from '@/next/link'
import { usePathname, useSearchParams } from '@/next/navigation'
import { cn } from '@/utils/classnames'
import CreatorUserMenu from './user-menu'

const COLLAPSED_STORAGE_KEY = 'creator-sidebar-collapsed'

// ChatGPT-style sidebar toggle icon
const SidebarToggleIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <line x1="9" y1="4" x2="9" y2="20" />
    <circle cx="6" cy="8" r="0.6" fill="currentColor" stroke="none" />
    <circle cx="6" cy="11" r="0.6" fill="currentColor" stroke="none" />
    <circle cx="6" cy="14" r="0.6" fill="currentColor" stroke="none" />
  </svg>
)

type NavItemProps = {
  href: string
  icon: React.ComponentType<{ className?: string }>
  label: string
  active: boolean
  collapsed: boolean
}

function NavItem({ href, icon: Icon, label, active, collapsed }: NavItemProps) {
  return (
    <Link
      href={href}
      aria-label={label}
      title={collapsed ? label : undefined}
      className={cn(
        'group/item relative flex cursor-default items-center rounded-lg text-sm font-medium transition-colors',
        collapsed ? 'h-10 w-10 justify-center' : 'gap-3 px-3 py-2',
        active
          ? 'bg-primary-50 text-primary-700'
          : 'text-text-secondary hover:bg-black/[0.04] hover:text-text-primary',
      )}
    >
      {active && !collapsed && (
        <span className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-primary-600" />
      )}
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  )
}

export default function CreatorSidebar() {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const { t } = useTranslation('socialPublish')
  const socialPublishEnabled = useGlobalPublicStore(
    s => s.systemFeatures.social_publish_enabled,
  )
  const [collapsed, setCollapsed] = useState(false)

  const selectedAppId = searchParams.get('app_id')
  const isCreatorHome = pathname === '/creator' && !selectedAppId
  const isCreatorWorks = pathname === '/creator-works'
  const isSocialPublish = pathname.startsWith('/creator/social-publish')

  // Hydrate collapsed state from localStorage on mount (client-only to avoid SSR mismatch)
  useEffect(() => {
    const stored = globalThis.localStorage?.getItem(COLLAPSED_STORAGE_KEY)

    if (stored === '1')
      setCollapsed(true) // eslint-disable-line react/set-state-in-effect
  }, [])

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev
      globalThis.localStorage?.setItem(COLLAPSED_STORAGE_KEY, next ? '1' : '0')
      return next
    })
  }

  return (
    <div
      className={cn(
        'relative h-full shrink-0 transition-[width] duration-200 ease-out',
        collapsed ? 'w-20' : 'w-64',
      )}
    >
      <aside className="flex h-full w-full flex-col border-r border-divider-subtle bg-white/60 backdrop-blur-xl">
        {/* Logo / Brand */}
        <div
          className={cn(
            'flex h-16 items-center border-b border-divider-subtle',
            collapsed ? 'justify-center px-0' : 'justify-between px-4',
          )}
        >
          {collapsed
            ? (
                <Tooltip>
                  <TooltipTrigger
                    delay={0}
                    render={(
                      <button
                        type="button"
                        onClick={toggleCollapsed}
                        aria-label="打开侧边栏"
                        aria-expanded={false}
                        className="group relative flex h-10 w-16 cursor-e-resize items-center justify-center rounded-md text-text-tertiary transition-colors hover:bg-black/[0.04] hover:text-text-primary"
                      >
                        <img
                          src="/logo/logo.svg"
                          alt="构界Agent"
                          className="h-5 w-auto transition-opacity group-hover:opacity-0 group-focus-visible:opacity-0"
                        />
                        <SidebarToggleIcon className="pointer-events-none absolute h-5 w-5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
                      </button>
                    )}
                  />
                  <TooltipContent placement="right">打开侧边栏</TooltipContent>
                </Tooltip>
              )
            : (
                <>
                  <Link
                    href="/creator"
                    aria-label="构界Agent 首页"
                    className="flex cursor-default items-center"
                  >
                    <img
                      src="/logo/logo.svg"
                      alt="构界Agent"
                      className="h-7 w-auto"
                    />
                  </Link>
                  <Tooltip>
                    <TooltipTrigger
                      delay={0}
                      render={(
                        <button
                          type="button"
                          onClick={toggleCollapsed}
                          aria-label="关闭侧边栏"
                          aria-expanded={true}
                          className="flex h-8 w-8 cursor-w-resize items-center justify-center rounded-md text-text-tertiary transition-colors hover:bg-black/[0.04] hover:text-text-primary"
                        >
                          <SidebarToggleIcon className="h-5 w-5" />
                        </button>
                      )}
                    />
                    <TooltipContent placement="bottom">关闭侧边栏</TooltipContent>
                  </Tooltip>
                </>
              )}
        </div>

        {/* Navigation */}
        <nav
          className={cn(
            'flex flex-1 flex-col overflow-y-auto py-5',
            collapsed ? 'items-center' : '',
          )}
        >
          {/* Home */}
          <div className={cn('mb-2', collapsed ? 'px-0' : 'px-3')}>
            <NavItem
              href="/creator"
              icon={RiHome4Line}
              label="首页"
              active={isCreatorHome}
              collapsed={collapsed}
            />
          </div>

          {/* Distribution section */}
          <div className={cn('mt-8', collapsed ? 'px-0' : 'px-3')}>
            {!collapsed && (
              <div className="mb-2 px-3">
                <span className="text-[11px] font-medium text-text-tertiary">
                  分发运营
                </span>
              </div>
            )}
            <NavItem
              href="/creator-works"
              icon={RiVideoLine}
              label="发布作品"
              active={isCreatorWorks}
              collapsed={collapsed}
            />
            {socialPublishEnabled && (
              <NavItem
                href="/creator/social-publish/accounts"
                icon={RiBroadcastLine}
                label={t('navTitle')}
                active={isSocialPublish}
                collapsed={collapsed}
              />
            )}
          </div>
        </nav>

        {/* Bottom user area */}
        <div
          className={cn(
            'border-t border-divider-subtle',
            collapsed ? 'p-2' : 'p-3',
          )}
        >
          <CreatorUserMenu collapsed={collapsed} />
        </div>
      </aside>
    </div>
  )
}
