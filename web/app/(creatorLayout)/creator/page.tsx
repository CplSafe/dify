'use client'

import type { FileEntity } from '@/app/components/base/file-uploader/types'
import { RiLoader4Line } from '@remixicon/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import { toast } from '@/app/components/base/ui/toast'
import { sanitizeDraftFiles, saveCreatorHomeDraft } from '@/app/components/creator/chat-draft'
import CreatorHomeInput from '@/app/components/creator/home-input'
import CreatorInstalledApp from '@/app/components/creator/installed-app-page'
import { get, post } from '@/service/base'
import { fetchInstalledAppList, fetchTrialAppParams } from '@/service/explore'

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
  const [homeAppParams, setHomeAppParams] = useState<any>(null)

  const isHome = !appId

  useEffect(() => {
    setLoadingApps(true)
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then(async (data) => {
        const apps = data.data || []
        setMarketplaceApps(apps)
        
        // Fetch params for the default home app to get visionConfig
        const defaultApp = apps.find(app => app.app_id === DEFAULT_CREATOR_HOME_APP_ID) || apps[0]
        if (defaultApp) {
          try {
            const params = await fetchTrialAppParams(defaultApp.app_id)
            setHomeAppParams(params)
          } catch (e) {
            console.error('Failed to fetch home app params', e)
          }
        }
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
    if (isHome || !appId) {
      setInstalledAppId(null)
      return
    }

    void ensureInstalledApp(appId)
  }, [ensureInstalledApp, appId, isHome])

  const handleHomeSubmit = (text: string, files: FileEntity[]) => {
    const defaultApp = marketplaceApps.find(app => app.app_id === DEFAULT_CREATOR_HOME_APP_ID) || marketplaceApps[0]
    if (!defaultApp) {
      toast.error('暂时没有可用的创作应用')
      return
    }

    saveCreatorHomeDraft({
      message: text,
      files: sanitizeDraftFiles(files),
    })
    router.push(`/creator?app_id=${defaultApp.app_id}`)
  }

  if (isHome) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center overflow-hidden bg-[#FBFBFF]">
        {/* Background blobs to match screenshot aesthetic */}
        <div className="absolute -left-[10%] -top-[10%] h-[50%] w-[50%] rounded-full bg-[#E0E9FF] opacity-40 blur-[120px]" />
        <div className="absolute -right-[5%] bottom-[10%] h-[40%] w-[40%] rounded-full bg-[#F3E8FF] opacity-50 blur-[100px]" />
        
        <div className="relative z-10 w-full">
          <CreatorHomeInput 
            onSubmit={handleHomeSubmit} 
            appParams={homeAppParams}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background-default">
      {loadingApps || installingAppId || !installedAppId
        ? (
            <div className="flex h-full min-h-[640px] flex-1 flex-col items-center justify-center gap-3 px-6">
              <RiLoader4Line className="h-7 w-7 animate-spin text-primary-600" />
              <div className="text-base font-medium text-text-primary">
                正在准备创作工作台
              </div>
              <div className="text-sm text-text-tertiary">
                {installError || '马上就好，正在连接应用对话能力。'}
              </div>
              {installError && appId && (
                <button
                  type="button"
                  className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
                  onClick={() => void ensureInstalledApp(appId)}
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
