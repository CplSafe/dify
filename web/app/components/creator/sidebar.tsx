'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { RiHome4Line, RiLayoutGridLine, RiVideoLine, RiAddLine, RiTimeLine } from '@remixicon/react'
import { cn } from '@/utils/classnames'
import { get } from '@/service/base'
import CreatorUserMenu from './user-menu'

type MarketplaceApp = {
  id: string
  app_id: string
  app_name: string
  app_description: string
  app_mode: string
  app_icon: string
  published_at: string
}

export default function CreatorSidebar() {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [marketplaceApps, setMarketplaceApps] = useState<MarketplaceApp[]>([])
  const [loading, setLoading] = useState(true)

  const selectedAppId = searchParams.get('app_id')
  const isCreatorInstalledPage = pathname.startsWith('/creator/installed/')
  const isCreatorHome = pathname === '/creator' && !selectedAppId

  useEffect(() => {
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then(data => setMarketplaceApps(data.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    if (diffDays === 0)
      return '今天'
    if (diffDays === 1)
      return '昨天'
    if (diffDays < 7)
      return `${diffDays}天前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  const isNew = (iso: string) => {
    const d = new Date(iso)
    const diffMs = Date.now() - d.getTime()
    return diffMs < 7 * 24 * 60 * 60 * 1000
  }

  return (
    <aside className="flex h-full w-64 flex-col border-r border-divider-subtle bg-background-sidebar">
      {/* Logo / Brand */}
      <div className="flex h-16 items-center px-5 border-b border-divider-subtle">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600">
            <RiVideoLine className="h-4 w-4 text-white" />
          </div>
          <span className="text-base font-semibold text-text-primary">创作Agent</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-1 flex-col overflow-y-auto py-4">
        {/* Home */}
        <div className="px-3 mb-2">
          <Link
            href="/creator"
            className={cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isCreatorHome
                ? 'bg-state-base-active text-text-primary'
                : 'text-text-secondary hover:bg-state-base-hover hover:text-text-primary',
            )}
          >
            <RiHome4Line className="h-4 w-4" />
            <span>首页</span>
          </Link>
        </div>

        {/* App Marketplace section */}
        <div className="px-3 mt-4">
          <div className="mb-2 flex items-center justify-between px-3">
            <span className="text-xs font-medium uppercase text-text-quaternary tracking-wider">创意中心</span>
          </div>

          {loading
            ? (
                <div className="px-3 py-2 text-xs text-text-quaternary">加载中...</div>
              )
            : marketplaceApps.length === 0
              ? (
                  <div className="px-3 py-2 text-xs text-text-quaternary">暂无应用</div>
                )
              : (
                  <div className="space-y-1">
                    {marketplaceApps.map(app => (
                      <Link
                        key={app.id}
                        href={`/creator?app_id=${app.app_id}`}
                        className={cn(
                          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                          (selectedAppId === app.app_id && (pathname === '/creator' || isCreatorInstalledPage))
                            ? 'bg-state-base-active text-text-primary'
                            : 'text-text-secondary hover:bg-state-base-hover hover:text-text-primary',
                        )}
                      >
                        <RiLayoutGridLine className="h-4 w-4 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1">
                            <span className="truncate text-sm">{app.app_name}</span>
                            {isNew(app.published_at) && (
                              <span className="shrink-0 rounded bg-primary-100 px-1 py-0.5 text-[10px] font-medium text-primary-700">NEW</span>
                            )}
                          </div>
                          <div className="flex items-center gap-1 text-xs text-text-quaternary">
                            <RiTimeLine className="h-3 w-3" />
                            <span>{formatDate(app.published_at)}</span>
                          </div>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}

          <Link
            href="/creator-marketplace"
            className={cn(
              'mt-1 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
              pathname === '/creator-marketplace'
                ? 'bg-state-base-active text-text-primary'
                : 'text-text-secondary hover:bg-state-base-hover hover:text-text-primary',
            )}
          >
            <RiAddLine className="h-4 w-4" />
            <span>应用市场</span>
          </Link>
        </div>

        {/* Distribution section */}
        <div className="px-3 mt-6">
          <div className="mb-2 flex items-center justify-between px-3">
            <span className="text-xs font-medium uppercase text-text-quaternary tracking-wider">分发运营</span>
          </div>
          <Link
            href="/creator-works"
            className={cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
              pathname === '/creator-works'
                ? 'bg-state-base-active text-text-primary'
                : 'text-text-secondary hover:bg-state-base-hover hover:text-text-primary',
            )}
          >
            <RiVideoLine className="h-4 w-4" />
            <span>发布作品</span>
          </Link>
        </div>
      </nav>

      {/* Bottom user area */}
      <div className="border-t border-divider-subtle p-3">
        <CreatorUserMenu />
      </div>
    </aside>
  )
}
