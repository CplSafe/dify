'use client'

import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { RiLoader4Line } from '@remixicon/react'
import { toast } from '@/app/components/base/ui/toast'
import CreatorInstalledApp from '@/app/components/creator/installed-app-page'
import { get, post } from '@/service/base'
import { fetchInstalledAppList } from '@/service/explore'

type MarketplaceApp = {
  id: string
  app_id: string
  app_name: string
  app_description: string
}

type InstallResponse = {
  installed_app_id: string
  already_installed: boolean
}

const DEFAULT_CREATOR_HOME_APP_ID = 'cd030efb-f7db-4972-a06e-83067cd20aa0'
const INSTALLED_APP_SYNC_RETRY_TIMES = 8
const INSTALLED_APP_SYNC_RETRY_DELAY = 250

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export default function CreatorPage() {
  const searchParams = useSearchParams()
  const appId = searchParams.get('app_id')

  const [marketplaceApps, setMarketplaceApps] = useState<MarketplaceApp[]>([])
  const [loadingApps, setLoadingApps] = useState(true)
  const [installingAppId, setInstallingAppId] = useState<string | null>(null)
  const [installError, setInstallError] = useState<string | null>(null)
  const [installedAppId, setInstalledAppId] = useState<string | null>(null)
  const [installedAppMap, setInstalledAppMap] = useState<Record<string, string>>({})

  const defaultHomepageApp = marketplaceApps.find(app => app.app_id === DEFAULT_CREATOR_HOME_APP_ID)
  const selectedAppId = appId || defaultHomepageApp?.app_id || marketplaceApps[0]?.app_id || null

  useEffect(() => {
    setLoadingApps(true)
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then(data => setMarketplaceApps(data.data || []))
      .catch(() => {
        toast.error('加载创作者应用失败')
      })
      .finally(() => setLoadingApps(false))
  }, [])

  const ensureInstalledApp = useCallback(async (nextAppId: string) => {
    setInstallingAppId(nextAppId)
    setInstallError(null)

    if (installedAppMap[nextAppId]) {
      setInstalledAppId(installedAppMap[nextAppId])
      setInstallingAppId(null)
      return
    }

    try {
      const data = await post<InstallResponse>(`/creator/marketplace/apps/${nextAppId}/install`, {
        body: {},
      })

      let readyInstalledAppId = data.installed_app_id
      for (let attempt = 0; attempt < INSTALLED_APP_SYNC_RETRY_TIMES; attempt++) {
        const installedData = await fetchInstalledAppList(nextAppId)
        const matchedInstalledApp = installedData.installed_apps.find(app => app.id === data.installed_app_id)

        if (matchedInstalledApp) {
          readyInstalledAppId = matchedInstalledApp.id
          break
        }

        if (attempt < INSTALLED_APP_SYNC_RETRY_TIMES - 1)
          await sleep(INSTALLED_APP_SYNC_RETRY_DELAY)
      }

      setInstalledAppMap(prev => ({ ...prev, [nextAppId]: readyInstalledAppId }))
      setInstalledAppId(readyInstalledAppId)
    }
    catch (error) {
      const message = error instanceof Error ? error.message : '打开应用失败，请稍后重试'
      setInstallError(message)
      toast.error(message)
      setInstalledAppId(null)
    }
    finally {
      setInstallingAppId(null)
    }
  }, [installedAppMap])

  useEffect(() => {
    if (!selectedAppId)
      return

    void ensureInstalledApp(selectedAppId)
  }, [ensureInstalledApp, selectedAppId])

  return (
    <div className="flex h-full min-h-0 flex-col bg-background-default">
      {loadingApps || !selectedAppId || installingAppId || !installedAppId
        ? (
            <div className="flex h-full min-h-[640px] flex-1 flex-col items-center justify-center gap-3 px-6">
              <RiLoader4Line className="h-7 w-7 animate-spin text-primary-600" />
              <div className="text-base font-medium text-text-primary">
                {selectedAppId ? '正在准备创作工作台' : '正在加载创作者应用'}
              </div>
              <div className="text-sm text-text-tertiary">
                {installError || '马上就好，正在连接应用对话能力。'}
              </div>
              {installError && selectedAppId && (
                <button
                  type="button"
                  className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
                  onClick={() => void ensureInstalledApp(selectedAppId)}
                >
                  重试
                </button>
              )}
            </div>
          )
        : (
            <CreatorInstalledApp
              installedAppId={installedAppId}
              marketplaceApps={marketplaceApps}
              layout="embedded"
            />
          )}
    </div>
  )
}
