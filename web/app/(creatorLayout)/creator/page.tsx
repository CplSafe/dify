'use client'

import { RiArrowLeftLine, RiLoader4Line } from '@remixicon/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import { toast } from '@/app/components/base/ui/toast'
import InstalledApp from '@/app/components/explore/installed-app'
import { get, post } from '@/service/base'
import { fetchInstalledAppList } from '@/service/explore'
import { cn } from '@/utils/classnames'

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
  const router = useRouter()
  const searchParams = useSearchParams()
  const appId = searchParams.get('app_id')

  const [marketplaceApps, setMarketplaceApps] = useState<MarketplaceApp[]>([])
  const [loadingApps, setLoadingApps] = useState(true)
  const [installingAppId, setInstallingAppId] = useState<string | null>(null)
  const [installError, setInstallError] = useState<string | null>(null)
  const [installedAppId, setInstalledAppId] = useState<string | null>(null)
  const [installedAppMap, setInstalledAppMap] = useState<Record<string, string>>({})

  const isHome = !appId
  const targetAppId = appId || DEFAULT_CREATOR_HOME_APP_ID

  useEffect(() => {
    setLoadingApps(true)
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then((data) => {
        setMarketplaceApps(data.data || [])
      })
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
    if (targetAppId && !loadingApps) {
      void ensureInstalledApp(targetAppId)
    }
  }, [targetAppId, loadingApps, ensureInstalledApp])

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-[#FBFBFF] overflow-hidden">
      {/* 保持和首页一样的背景氛围 */}
      <div className="absolute -left-[10%] -top-[10%] h-[50%] w-[50%] rounded-full bg-[#E0E9FF] opacity-40 blur-[120px] pointer-events-none" />
      <div className="absolute -right-[5%] bottom-[10%] h-[40%] w-[40%] rounded-full bg-[#F3E8FF] opacity-50 blur-[100px] pointer-events-none" />

      {/* 顶部返回栏，仅在非首页时显示 */}
      {!isHome && (
        <div className="relative z-10 flex shrink-0 items-center px-4 py-3">
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-[#4D4D54] transition-all hover:bg-white/60 active:scale-95"
            onClick={() => router.push('/creator')}
          >
            <RiArrowLeftLine className="h-4 w-4" />
            <span>返回首页</span>
          </button>
        </div>
      )}

      {/* webapp 完整界面 */}
      <div className={cn("relative z-10 min-h-0 flex-1", !isHome && "px-2 pb-2")}>
        {loadingApps || installingAppId || !installedAppId
          ? (
            <div className="flex h-full flex-col items-center justify-center gap-3">
              <RiLoader4Line className="h-7 w-7 animate-spin text-primary-600" />
              <div className="text-base font-medium text-text-primary">正在准备创作工作台</div>
              <div className="text-sm text-text-tertiary">
                {installError || '马上就好，正在连接应用。'}
              </div>
              {installError && (
                <button
                  type="button"
                  className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
                  onClick={() => void ensureInstalledApp(targetAppId)}
                >
                  重试
                </button>
              )}
            </div>
          )
          : (
            <div className={cn("h-full w-full", !isHome && "rounded-2xl bg-white/80 shadow-sm backdrop-blur-sm overflow-hidden border border-white")}>
              <InstalledApp id={installedAppId} />
            </div>
          )}
      </div>
    </div>
  )
}
