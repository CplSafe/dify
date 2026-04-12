'use client'

import type { FileEntity } from '@/app/components/base/file-uploader/types'
import { RiArrowLeftLine, RiLoader4Line } from '@remixicon/react'
import { useCallback, useEffect, useRef, useState } from 'react'
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
  const [marketplaceApps, setMarketplaceApps] = useState<MarketplaceApp[]>([])
  const [loadingApps, setLoadingApps] = useState(true)
  const [installingAppId, setInstallingAppId] = useState<string | null>(null)
  const [installError, setInstallError] = useState<string | null>(null)
  const [installedAppId, setInstalledAppId] = useState<string | null>(null)
  const [installedAppMap, setInstalledAppMap] = useState<Record<string, string>>({})
  const [homeAppParams, setHomeAppParams] = useState<any>(null)

  // 控制是否显示对话界面（不跳转页面）
  const [activeAppId, setActiveAppId] = useState<string | null>(null)
  const hasStartedRef = useRef(false)

  const isHome = !activeAppId

  useEffect(() => {
    setLoadingApps(true)
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then(async (data) => {
        const apps = data.data || []
        setMarketplaceApps(apps)

        const defaultApp = apps.find(app => app.app_id === DEFAULT_CREATOR_HOME_APP_ID) || apps[0]
        if (defaultApp) {
          try {
            const params = await fetchTrialAppParams(defaultApp.app_id)
            setHomeAppParams(params)
          }
          catch (e) {
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

  // 当 activeAppId 变化时自动安装应用
  useEffect(() => {
    if (!activeAppId) {
      setInstalledAppId(null)
      return
    }

    void ensureInstalledApp(activeAppId)
  }, [ensureInstalledApp, activeAppId])

  const handleHomeSubmit = (text: string, files: FileEntity[]) => {
    const defaultApp = marketplaceApps.find(app => app.app_id === DEFAULT_CREATOR_HOME_APP_ID) || marketplaceApps[0]
    if (!defaultApp) {
      toast.error('暂时没有可用的创作应用')
      return
    }

    // 保存草稿，供 InstalledApp 读取并自动发送
    saveCreatorHomeDraft({
      message: text,
      files: sanitizeDraftFiles(files),
    })

    hasStartedRef.current = true
    // 不跳转页面，直接切换到对话模式
    setActiveAppId(defaultApp.app_id)
  }

  const handleBackToHome = () => {
    setActiveAppId(null)
    setInstalledAppId(null)
    hasStartedRef.current = false
  }

  // 首页：显示输入框
  if (isHome) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center overflow-hidden bg-[#FBFBFF]">
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

  // 对话模式：在当前页面内展示，带返回按钮
  return (
    <div className="flex h-full min-h-0 flex-col bg-background-default">
      {/* 顶部返回栏 */}
      <div className="flex shrink-0 items-center gap-2 border-b border-divider-subtle px-4 py-2">
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-text-secondary transition-colors hover:bg-state-base-hover"
          onClick={handleBackToHome}
        >
          <RiArrowLeftLine className="h-4 w-4" />
          <span>返回首页</span>
        </button>
      </div>

      {/* 对话内容区 */}
      <div className="min-h-0 flex-1">
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
              {installError && activeAppId && (
                <button
                  type="button"
                  className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
                  onClick={() => void ensureInstalledApp(activeAppId)}
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
    </div>
  )
}
