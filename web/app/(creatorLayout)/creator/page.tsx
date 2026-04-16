'use client'
/* eslint-disable no-restricted-imports, ts/no-explicit-any, react/set-state-in-effect, tailwindcss/enforce-consistent-class-order -- TODO(wallet): preexisting issues tracked for a follow-up cleanup */

import type { CreatorChatDraft } from '@/app/components/creator/chat-draft'
import { RiArrowLeftLine, RiLoader4Line } from '@remixicon/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from '@/app/components/base/ui/toast'
import { sanitizeDraftFiles } from '@/app/components/creator/chat-draft'
import CreatorHomeInput from '@/app/components/creator/home-input'
import InstalledApp from '@/app/components/explore/installed-app'
import { get, post } from '@/service/base'
import { createCreatorTask, updateCreatorTask } from '@/service/creator-task'
import { fetchInstalledAppList, fetchTrialAppParams } from '@/service/explore'
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

  const [loadingApps, setLoadingApps] = useState(true)
  const [installingAppId, setInstallingAppId] = useState<string | null>(null)
  const [installError, setInstallError] = useState<string | null>(null)
  const [installedAppId, setInstalledAppId] = useState<string | null>(null)
  const [installedAppMap, setInstalledAppMap] = useState<
    Record<string, string>
  >({})
  const [workspaceOpen, setWorkspaceOpen] = useState(() => !!appId)
  const [initialDraft, setInitialDraft] = useState<CreatorChatDraft | null>(
    null,
  )
  const [homeAppParams, setHomeAppParams] = useState<any>(null)
  const [workspaceSessionKey, setWorkspaceSessionKey] = useState(() =>
    crypto.randomUUID(),
  )
  const [workspaceIsFreshConversation, setWorkspaceIsFreshConversation]
    = useState(() => !appId)

  const isHome = !appId
  const targetAppId = appId || DEFAULT_CREATOR_HOME_APP_ID

  useEffect(() => {
    setLoadingApps(true)
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then(() => {})
      .catch(() => {
        toast.error('加载创作者应用失败')
      })
      .finally(() => setLoadingApps(false))
  }, [])

  useEffect(() => {
    if (!isHome) {
      setWorkspaceOpen(true)
      return
    }

    fetchTrialAppParams(targetAppId)
      .then((params) => {
        setHomeAppParams(params)
      })
      .catch(() => {
        setHomeAppParams(null)
      })
  }, [isHome, targetAppId])

  const ensureInstalledApp = useCallback(
    async (nextAppId: string) => {
      setInstallingAppId(nextAppId)
      setInstallError(null)

      if (installedAppMap[nextAppId]) {
        setInstalledAppId(installedAppMap[nextAppId])
        setInstallingAppId(null)
        return
      }

      try {
        const data = await post<InstallResponse>(
          `/creator/marketplace/apps/${nextAppId}/install`,
          {
            body: {},
          },
        )

        let readyInstalledAppId = data.installed_app_id
        for (
          let attempt = 0;
          attempt < INSTALLED_APP_SYNC_RETRY_TIMES;
          attempt++
        ) {
          const installedData = await fetchInstalledAppList(nextAppId)
          const matchedInstalledApp = installedData.installed_apps.find(
            app => app.id === data.installed_app_id,
          )

          if (matchedInstalledApp) {
            readyInstalledAppId = matchedInstalledApp.id
            break
          }

          if (attempt < INSTALLED_APP_SYNC_RETRY_TIMES - 1)
            await sleep(INSTALLED_APP_SYNC_RETRY_DELAY)
        }

        setInstalledAppMap(prev => ({
          ...prev,
          [nextAppId]: readyInstalledAppId,
        }))
        setInstalledAppId(readyInstalledAppId)
      }
      catch (error) {
        const message
          = error instanceof Error ? error.message : '打开应用失败，请稍后重试'
        setInstallError(message)
        toast.error(message)
        setInstalledAppId(null)
      }
      finally {
        setInstallingAppId(null)
      }
    },
    [installedAppMap],
  )

  useEffect(() => {
    if ((workspaceOpen || !isHome) && targetAppId && !loadingApps)
      void ensureInstalledApp(targetAppId)
  }, [workspaceOpen, isHome, targetAppId, loadingApps, ensureInstalledApp])

  const handleOpenWorkspace = useCallback(
    (draft?: Omit<CreatorChatDraft, 'id'>) => {
      setWorkspaceSessionKey(crypto.randomUUID())
      setWorkspaceIsFreshConversation(true)
      if (draft) {
        setInitialDraft({
          id: crypto.randomUUID(),
          message: draft.message,
          files: draft.files,
          inputs: draft.inputs,
        })
      }
      setWorkspaceOpen(true)
    },
    [],
  )

  const currentTaskIdRef = useRef<string | null>(null)

  const handleMessageStart = useCallback(
    async ({
      installedAppId: iAppId,
      conversationId,
      appName,
    }: {
      installedAppId: string
      conversationId: string | null
      appName?: string
    }) => {
      try {
        const task = await createCreatorTask({
          app_id: targetAppId,
          installed_app_id: iAppId,
          conversation_id: conversationId ?? undefined,
          title: appName || '创作任务',
        })
        currentTaskIdRef.current = task.id
      }
      catch {
        // Non-critical: task tracking failure should not block the chat flow
      }
    },
    [targetAppId],
  )

  const handleResultCompleted = useCallback(async (_payload: unknown) => {
    if (currentTaskIdRef.current) {
      updateCreatorTask(currentTaskIdRef.current, {
        status: 'completed',
      }).catch(() => {})
      currentTaskIdRef.current = null
    }
  }, [])

  const showWorkspace = workspaceOpen || !isHome

  const handleBack = useCallback(() => {
    if (!isHome) {
      router.push('/creator')
      return
    }

    setWorkspaceOpen(false)
    setInitialDraft(null)
    setWorkspaceIsFreshConversation(true)
    setWorkspaceSessionKey(crypto.randomUUID())
  }, [isHome, router])

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-[#FBFBFF]">
      <div className="pointer-events-none absolute -left-[10%] -top-[10%] h-[50%] w-[50%] rounded-full bg-[#E0E9FF] opacity-40 blur-[120px]" />
      <div className="pointer-events-none absolute -right-[5%] bottom-[10%] h-[40%] w-[40%] rounded-full bg-[#F3E8FF] opacity-50 blur-[100px]" />

      {showWorkspace && (
        <div className="relative z-10 flex shrink-0 items-center px-4 py-3">
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-white/60 hover:text-text-primary active:bg-white/80"
            onClick={handleBack}
          >
            <RiArrowLeftLine className="h-4 w-4" />
            <span>返回首页</span>
          </button>
        </div>
      )}

      <div
        className={cn(
          'relative z-10 min-h-0 flex-1',
          showWorkspace && 'px-2 pb-2',
        )}
      >
        {!showWorkspace && (
          <div className="flex h-full w-full flex-col items-center justify-center pt-[10vh]">
            <CreatorHomeInput
              appParams={homeAppParams}
              onSubmit={(text, files, inputs) => {
                handleOpenWorkspace({
                  message: text,
                  files: sanitizeDraftFiles(files),
                  inputs,
                })
              }}
            />
          </div>
        )}

        {showWorkspace
          && (loadingApps || installingAppId || !installedAppId)
          ? (
              <div className="flex h-full flex-col items-center justify-center gap-3">
                <RiLoader4Line className="h-7 w-7 animate-spin text-primary-600" />
                <div className="text-base font-medium text-text-primary">
                  正在准备创作工作台
                </div>
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
          : null}

        {showWorkspace
          && installedAppId
          && !loadingApps
          && !installingAppId && (
          <div className="h-full w-full overflow-hidden rounded-2xl border border-white bg-white/80 shadow-sm backdrop-blur-sm">
            <InstalledApp
              key={`${installedAppId}:${workspaceSessionKey}`}
              id={installedAppId}
              initialDraft={initialDraft}
              forceFreshConversation={workspaceIsFreshConversation}
              onInitialDraftConsumed={() => setInitialDraft(null)}
              onMessageStart={handleMessageStart}
              onResultCompleted={handleResultCompleted}
            />
          </div>
        )}
      </div>
    </div>
  )
}
