'use client'

import type { GeneratedResultPayload } from '@/app/components/share/generated-result'
import type { InstalledApp as InstalledAppType } from '@/models/explore'
import { RiLoader4Line } from '@remixicon/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import AppUnavailable from '@/app/components/base/app-unavailable'
import { clearCreatorHomeDraft, getCreatorHomeDraft } from '@/app/components/creator/chat-draft'
import InstalledApp from '@/app/components/explore/installed-app'
import { get, post } from '@/service/base'
import { fetchInstalledAppList } from '@/service/explore'

type MarketplaceApp = {
  id: string
  app_id: string
  app_name: string
  app_description: string
}

type CreatorInstalledAppProps = {
  installedAppId: string
  marketplaceApps?: MarketplaceApp[]
  layout?: 'full' | 'embedded'
}

export default function CreatorInstalledApp({
  installedAppId,
  marketplaceApps: initialMarketplaceApps,
  layout = 'full',
}: CreatorInstalledAppProps) {
  const [marketplaceApps, setMarketplaceApps] = useState<MarketplaceApp[]>(initialMarketplaceApps || [])
  const [installedApp, setInstalledApp] = useState<InstalledAppType | null>(null)
  const [loading, setLoading] = useState(!initialMarketplaceApps)
  const [isSavingWork, setIsSavingWork] = useState(false)
  const [savedResultIds, setSavedResultIds] = useState<Record<string, true>>({})
  const [initialDraft, setInitialDraft] = useState(() => getCreatorHomeDraft())

  useEffect(() => {
    setLoading(true)
    const loadMarketplaceApps = initialMarketplaceApps
      ? Promise.resolve({ data: initialMarketplaceApps })
      : get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')

    Promise.all([
      loadMarketplaceApps,
      fetchInstalledAppList(),
    ])
      .then(([marketplaceData, installedData]) => {
        setMarketplaceApps(marketplaceData.data || [])
        setInstalledApp(installedData.installed_apps.find(app => app.id === installedAppId) || null)
      })
      .catch(() => {
        setMarketplaceApps([])
        setInstalledApp(null)
      })
      .finally(() => setLoading(false))
  }, [initialMarketplaceApps, installedAppId])

  useEffect(() => {
    setInitialDraft(getCreatorHomeDraft())
  }, [installedAppId])

  const creatorAppIds = useMemo(() => new Set(marketplaceApps.map(app => app.app_id)), [marketplaceApps])
  const isValidCreatorInstalledApp = !!installedApp && creatorAppIds.has(installedApp.app.id)

  const buildWorkTitle = useCallback((payload: GeneratedResultPayload) => {
    const firstInputString = Object.values(payload.inputs || {}).find(value => typeof value === 'string' && value.trim().length > 0)
    const preferred = payload.query || firstInputString || payload.content

    return String(preferred).slice(0, 60) || installedApp?.app.name || 'Untitled'
  }, [installedApp?.app.name])

  const handleResultCompleted = useCallback(async (payload: GeneratedResultPayload) => {
    const resultKey = payload.workflowRunId || payload.messageId
    if (!payload.success || !payload.content || !installedApp || !resultKey || savedResultIds[resultKey])
      return

    setIsSavingWork(true)
    try {
      await post('/creator/works', {
        body: {
          title: buildWorkTitle(payload),
          app_id: installedApp.app.id,
          workflow_run_id: resultKey,
          output_data: payload.content,
        },
      })
      setSavedResultIds(prev => ({ ...prev, [resultKey]: true }))
    }
    catch {
      // Avoid interrupting the creator chat flow if persistence fails.
    }
    finally {
      setIsSavingWork(false)
    }
  }, [buildWorkTitle, installedApp, savedResultIds])

  return (
    <div className="flex h-full min-h-0 flex-col bg-background-body">
      {layout === 'full' && (
        <div className="shrink-0 border-b border-divider-subtle bg-background-default px-6 py-3">
          {loading
            ? (
                <div className="flex items-center gap-2 py-2 text-sm text-text-tertiary">
                  <RiLoader4Line className="h-4 w-4 animate-spin" />
                  加载应用列表中...
                </div>
              )
            : !isValidCreatorInstalledApp
                ? (
                    <div className="py-2 text-sm text-text-tertiary">
                      当前应用不属于创作者专区。
                    </div>
                  )
                : (
                    <div>
                      <h1 className="text-base font-semibold text-text-primary">创作者对话工作台</h1>
                      <p className="mt-1 text-sm text-text-tertiary">复用应用原生对话能力，在创作者专区内直接完成创作。</p>
                    </div>
                  )}
        </div>
      )}

      <div className="min-h-0 flex-1">
        {loading && (
          <div className="flex h-full items-center justify-center">
            <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
          </div>
        )}
        {!loading && !isValidCreatorInstalledApp && (
          <div className="flex h-full items-center justify-center">
            <AppUnavailable code={404} unknownReason="Creator app not found." />
          </div>
        )}
        {!loading && isValidCreatorInstalledApp && (
          <div className="relative h-full">
            {isSavingWork && (
              <div className="pointer-events-none absolute right-4 top-4 z-10 rounded-full bg-components-panel-bg-blur px-3 py-1 text-xs text-text-tertiary shadow-sm backdrop-blur-xs">
                正在保存到近期创作...
              </div>
            )}
            <InstalledApp
              id={installedAppId}
              initialDraft={initialDraft}
              onInitialDraftConsumed={() => {
                clearCreatorHomeDraft()
                setInitialDraft(null)
              }}
              onResultCompleted={handleResultCompleted}
            />
          </div>
        )}
      </div>
    </div>
  )
}
