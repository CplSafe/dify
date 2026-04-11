'use client'

import { useEffect, useState } from 'react'
import { RiLayoutGridLine, RiTimeLine, RiDeleteBin6Line, RiAddLine } from '@remixicon/react'
import { useAppContext } from '@/context/app-context'
import { useRouter } from 'next/navigation'

type App = {
  id: string
  name: string
  description: string
  mode: string
  icon: string
}

type MarketplaceApp = {
  id: string
  app_id: string
  app_name: string
  app_description: string
  app_mode: string
  published_at: string
  published_by_name: string
}

export default function AdminMarketplacePage() {
  const { isSystemAdmin, isLoadingCurrentWorkspace } = useAppContext()
  const router = useRouter()
  const [publishedApps, setPublishedApps] = useState<MarketplaceApp[]>([])
  const [availableApps, setAvailableApps] = useState<App[]>([])
  const [loading, setLoading] = useState(true)
  const [publishingId, setPublishingId] = useState<string | null>(null)
  const [removingId, setRemovingId] = useState<string | null>(null)

  useEffect(() => {
    if (!isLoadingCurrentWorkspace && !isSystemAdmin) {
      router.replace('/apps')
    }
  }, [isSystemAdmin, isLoadingCurrentWorkspace, router])

  const loadData = () => {
    if (!isSystemAdmin)
      return
    Promise.all([
      fetch('/console/api/creator/marketplace/apps').then(r => r.json()),
      fetch('/console/api/apps?page=1&limit=100').then(r => r.json()),
    ]).then(([marketData, appsData]) => {
      setPublishedApps(marketData.data || [])
      setAvailableApps(appsData.data || [])
    }).catch(() => {}).finally(() => setLoading(false))
  }

  useEffect(() => {
    loadData()
  }, [isSystemAdmin])

  const handlePublish = async (appId: string) => {
    setPublishingId(appId)
    try {
      const resp = await fetch('/console/api/creator/marketplace/apps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app_id: appId }),
      })
      if (resp.ok)
        loadData()
    }
    catch {}
    finally {
      setPublishingId(null)
    }
  }

  const handleRemove = async (appId: string) => {
    if (!confirm('确认将此应用从市场下架？'))
      return
    setRemovingId(appId)
    try {
      await fetch(`/console/api/creator/marketplace/apps/${appId}`, { method: 'DELETE' })
      loadData()
    }
    catch {}
    finally {
      setRemovingId(null)
    }
  }

  const publishedAppIds = new Set(publishedApps.map(a => a.app_id))
  const unpublishedApps = availableApps.filter(a => !publishedAppIds.has(a.id))

  if (!isSystemAdmin && !isLoadingCurrentWorkspace)
    return null

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-divider-subtle px-8 py-6">
        <h1 className="text-2xl font-bold text-text-primary">应用市场管理</h1>
        <p className="mt-1 text-text-quaternary">发布工作流应用到市场，供所有用户使用</p>
      </div>

      <div className="flex-1 p-8 space-y-8">
        {/* Published apps */}
        <div>
          <h2 className="mb-4 flex items-center gap-2 font-semibold text-text-primary">
            <RiLayoutGridLine className="h-5 w-5 text-primary-600" />
            已发布应用
            <span className="rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary-700">
              {publishedApps.length}
            </span>
          </h2>

          {loading
            ? <div className="py-8 text-center text-text-quaternary">加载中...</div>
            : publishedApps.length === 0
              ? (
                  <div className="rounded-2xl border border-dashed border-divider-subtle py-12 text-center text-text-quaternary">
                    暂无已发布的应用，从下方选择应用发布到市场
                  </div>
                )
              : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {publishedApps.map(app => (
                      <div
                        key={app.id}
                        className="flex items-center justify-between rounded-xl border border-divider-subtle bg-background-default p-4"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-text-primary truncate">{app.app_name}</div>
                          <div className="flex items-center gap-1 text-xs text-text-quaternary mt-0.5">
                            <RiTimeLine className="h-3 w-3" />
                            <span>{new Date(app.published_at).toLocaleDateString('zh-CN')}</span>
                          </div>
                        </div>
                        <button
                          onClick={() => handleRemove(app.app_id)}
                          disabled={removingId === app.app_id}
                          className="ml-3 text-text-quaternary hover:text-state-destructive transition-colors disabled:opacity-50"
                          title="下架"
                        >
                          <RiDeleteBin6Line className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
        </div>

        {/* Available apps to publish */}
        <div>
          <h2 className="mb-4 flex items-center gap-2 font-semibold text-text-primary">
            <RiAddLine className="h-5 w-5 text-green-600" />
            可发布的应用
          </h2>

          {loading
            ? null
            : unpublishedApps.length === 0
              ? (
                  <div className="rounded-2xl border border-dashed border-divider-subtle py-12 text-center text-text-quaternary">
                    所有应用均已发布到市场
                  </div>
                )
              : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {unpublishedApps.map(app => (
                      <div
                        key={app.id}
                        className="flex items-center justify-between rounded-xl border border-divider-subtle bg-background-default p-4 hover:border-primary-300 transition-colors"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-text-primary truncate">{app.name}</div>
                          <div className="text-xs text-text-quaternary mt-0.5 truncate">
                            {app.description || '无描述'}
                          </div>
                          <span className="mt-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-600">
                            {app.mode}
                          </span>
                        </div>
                        <button
                          onClick={() => handlePublish(app.id)}
                          disabled={publishingId === app.id}
                          className="ml-3 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-50 transition-colors whitespace-nowrap"
                        >
                          {publishingId === app.id ? '发布中...' : '发布'}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
        </div>
      </div>
    </div>
  )
}
