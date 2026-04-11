'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { RiArrowRightLine, RiChat3Line, RiLayoutGridLine, RiTimeLine, RiVideoLine } from '@remixicon/react'
import { get } from '@/service/base'
import { cn } from '@/utils/classnames'

type MarketplaceApp = {
  id: string
  app_id: string
  app_name: string
  app_description: string
  app_mode: string
  app_icon: string
  app_icon_type: string
  app_icon_background: string
  icon_url: string | null
  published_at: string
  published_by_name: string
  display_order: number
}

function AppIcon({ app }: { app: MarketplaceApp }) {
  if (app.app_icon_type === 'image' && app.icon_url) {
    return (
      <img
        src={app.icon_url}
        alt={app.app_name}
        className="h-full w-full object-cover"
      />
    )
  }
  // emoji icon
  return (
    <span className="text-2xl leading-none">
      {app.app_icon || getModeEmoji(app.app_mode)}
    </span>
  )
}

function getModeEmoji(mode: string) {
  if (mode === 'workflow')
    return '⚡'
  if (mode === 'advanced-chat' || mode === 'chat')
    return '💬'
  return '🤖'
}

function getModeIcon(mode: string) {
  if (mode === 'workflow')
    return <RiLayoutGridLine className="h-4 w-4" />
  if (mode === 'advanced-chat' || mode === 'chat')
    return <RiChat3Line className="h-4 w-4" />
  return <RiVideoLine className="h-4 w-4" />
}

function getModeLabel(mode: string) {
  if (mode === 'workflow')
    return '工作流'
  if (mode === 'advanced-chat')
    return '高级对话'
  if (mode === 'chat')
    return '对话'
  return mode
}

export default function CreatorMarketplacePage() {
  const [apps, setApps] = useState<MarketplaceApp[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then(data => setApps(data.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
  }

  const isNew = (iso: string) => {
    return Date.now() - new Date(iso).getTime() < 7 * 24 * 60 * 60 * 1000
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-divider-subtle px-8 py-6">
        <h1 className="text-2xl font-bold text-text-primary">应用市场</h1>
        <p className="mt-1 text-text-quaternary">探索并使用由管理员发布的 AI 工作流应用</p>
      </div>

      <div className="flex-1 p-8">
        {loading
          ? (
              <div className="flex h-48 items-center justify-center text-text-quaternary">
                加载中...
              </div>
            )
          : apps.length === 0
            ? (
                <div className="flex h-48 flex-col items-center justify-center text-text-quaternary">
                  <RiLayoutGridLine className="mb-3 h-12 w-12 opacity-30" />
                  <p>暂无已发布的应用</p>
                  <p className="mt-1 text-sm">管理员发布应用后，将在此显示</p>
                </div>
              )
            : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {apps.map(app => (
                    <Link
                      key={app.id}
                      href={`/creator?app_id=${app.app_id}`}
                      className="group flex flex-col rounded-2xl border border-divider-subtle bg-background-default p-5 transition-all hover:border-primary-300 hover:shadow-md"
                    >
                      {/* Header: icon + badges */}
                      <div className="mb-4 flex items-start justify-between">
                        <div
                          className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-xl"
                          style={{
                            background: app.app_icon_type === 'image'
                              ? undefined
                              : (app.app_icon_background || '#E0E0FF'),
                          }}
                        >
                          <AppIcon app={app} />
                        </div>
                        <div className="flex items-center gap-1.5">
                          {isNew(app.published_at) && (
                            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">NEW</span>
                          )}
                          <span className={cn(
                            'flex items-center gap-1 rounded-full px-2 py-0.5 text-xs text-text-tertiary',
                            'bg-background-default-dimm border border-divider-subtle',
                          )}>
                            {getModeIcon(app.app_mode)}
                            {getModeLabel(app.app_mode)}
                          </span>
                        </div>
                      </div>

                      {/* Name & description */}
                      <h3 className="mb-1 font-semibold text-text-primary transition-colors group-hover:text-primary-600">
                        {app.app_name}
                      </h3>
                      <p className="flex-1 line-clamp-2 text-sm text-text-quaternary">
                        {app.app_description || '点击开始使用此应用'}
                      </p>

                      {/* Footer */}
                      <div className="mt-4 flex items-center justify-between">
                        <div className="flex items-center gap-3 text-xs text-text-quaternary">
                          <div className="flex items-center gap-1">
                            <RiTimeLine className="h-3 w-3" />
                            <span>{formatDate(app.published_at)}</span>
                          </div>
                          {app.published_by_name && (
                            <span>by {app.published_by_name}</span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 text-xs font-medium text-primary-600 opacity-0 transition-opacity group-hover:opacity-100">
                          <span>开始使用</span>
                          <RiArrowRightLine className="h-3 w-3" />
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
      </div>
    </div>
  )
}
