'use client'

import type { FileEntity } from '@/app/components/base/file-uploader/types'
import { RiArrowLeftLine, RiLoader4Line } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import { toast } from '@/app/components/base/ui/toast'
import { sanitizeDraftFiles, saveCreatorHomeDraft } from '@/app/components/creator/chat-draft'
import CreatorHomeInput from '@/app/components/creator/home-input'
import InstalledApp from '@/app/components/explore/installed-app'
import { get, post } from '@/service/base'
import { fetchInstalledAppList } from '@/service/explore'

type DefaultAppInfo = {
  app_id: string
  app_name: string
  app_mode: string
}

type InstallResponse = {
  installed_app_id: string
  already_installed: boolean
}

const INSTALLED_APP_SYNC_RETRY_TIMES = 8
const INSTALLED_APP_SYNC_RETRY_DELAY = 250

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export default function CreatorPage() {
  // 默认应用信息（从后端读取）
  const [defaultApp, setDefaultApp] = useState<DefaultAppInfo | null>(null)
  const [loadingDefault, setLoadingDefault] = useState(true)

  // 安装状态
  const [installedAppId, setInstalledAppId] = useState<string | null>(null)
  const [installing, setInstalling] = useState(false)
  const [installError, setInstallError] = useState<string | null>(null)

  // 是否已开始工作流（隐藏首页输入框）
  const [started, setStarted] = useState(false)

  // 1. 页面加载时读取默认应用
  useEffect(() => {
    setLoadingDefault(true)
    get<{ data: DefaultAppInfo | null }>('/creator/marketplace/default-app')
      .then((res) => {
        setDefaultApp(res.data)
      })
      .catch(() => {
        toast.error('加载默认应用失败')
      })
      .finally(() => setLoadingDefault(false))
  }, [])

  // 2. 拿到默认应用后，预装它
  const ensureInstalledApp = useCallback(async (appId: string) => {
    setInstalling(true)
    setInstallError(null)

    try {
      const data = await post<InstallResponse>(`/creator/marketplace/apps/${appId}/install`, {
        body: {},
      })

      let readyId = data.installed_app_id
      for (let attempt = 0; attempt < INSTALLED_APP_SYNC_RETRY_TIMES; attempt++) {
        const installedData = await fetchInstalledAppList(appId)
        const matched = installedData.installed_apps.find(app => app.id === data.installed_app_id)
        if (matched) {
          readyId = matched.id
          break
        }
        if (attempt < INSTALLED_APP_SYNC_RETRY_TIMES - 1)
          await sleep(INSTALLED_APP_SYNC_RETRY_DELAY)
      }

      setInstalledAppId(readyId)
    }
    catch (error) {
      const message = error instanceof Error ? error.message : '连接应用失败，请稍后重试'
      setInstallError(message)
      toast.error(message)
    }
    finally {
      setInstalling(false)
    }
  }, [])

  useEffect(() => {
    if (defaultApp?.app_id) {
      void ensureInstalledApp(defaultApp.app_id)
    }
  }, [defaultApp?.app_id, ensureInstalledApp])

  // 3. 首页提交 → 保存草稿 → 隐藏输入框 → 显示 webapp
  const handleHomeSubmit = (text: string, files: FileEntity[]) => {
    if (!defaultApp) {
      toast.error('暂无可用的创作应用，请联系管理员设置默认应用')
      return
    }
    if (!installedAppId) {
      toast.error('应用正在加载中，请稍后')
      return
    }

    saveCreatorHomeDraft({
      message: text,
      files: sanitizeDraftFiles(files),
    })

    setStarted(true)
  }

  // 4. 返回首页（重新显示输入框）
  const handleBackToHome = () => {
    setStarted(false)
  }

  // 加载默认应用中
  if (loadingDefault) {
    return (
      <div className="flex h-full items-center justify-center">
        <RiLoader4Line className="h-6 w-6 animate-spin text-primary-600" />
      </div>
    )
  }

  // 没有设置默认应用
  if (!defaultApp) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <div className="text-base font-medium text-text-primary">暂无默认创作应用</div>
        <div className="text-sm text-text-tertiary">请联系管理员在后台发布应用并设置为默认</div>
      </div>
    )
  }

  // ===== 首页：显示输入框 =====
  if (!started) {
    return (
      <div className="relative flex h-full flex-col items-center justify-center overflow-hidden bg-[#FBFBFF]">
        <div className="absolute -left-[10%] -top-[10%] h-[50%] w-[50%] rounded-full bg-[#E0E9FF] opacity-40 blur-[120px]" />
        <div className="absolute -right-[5%] bottom-[10%] h-[40%] w-[40%] rounded-full bg-[#F3E8FF] opacity-50 blur-[100px]" />

        <div className="relative z-10 w-full">
          <CreatorHomeInput onSubmit={handleHomeSubmit} />
        </div>

        {installing && (
          <div className="absolute bottom-8 flex items-center gap-2 text-sm text-text-quaternary">
            <RiLoader4Line className="h-4 w-4 animate-spin" />
            正在预加载应用...
          </div>
        )}
      </div>
    )
  }

  // ===== 工作流/对话模式：显示完整 webapp（含侧边栏），隐藏首页输入框 =====
  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 顶部返回栏 */}
      <div className="flex shrink-0 items-center border-b border-divider-subtle bg-background-default px-4 py-2">
        <button
          type="button"
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-text-secondary transition-colors hover:bg-state-base-hover"
          onClick={handleBackToHome}
        >
          <RiArrowLeftLine className="h-4 w-4" />
          <span>新建创作</span>
        </button>
      </div>

      {/* webapp 完整界面 */}
      <div className="min-h-0 flex-1">
        {!installedAppId
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
                  onClick={() => void ensureInstalledApp(defaultApp.app_id)}
                >
                  重试
                </button>
              )}
            </div>
          )
          : (
            <InstalledApp id={installedAppId} />
          )}
      </div>
    </div>
  )
}
