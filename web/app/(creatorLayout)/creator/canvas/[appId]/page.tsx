'use client'
/* eslint-disable react/set-state-in-effect -- single-shot auth probe; Suspense not warranted for CR3 shell */

import type { InstalledApp as ExploreInstalledApp } from '@/models/explore'
import { useCallback, useEffect, useState } from 'react'
import CanvasRuntime from '@/app/components/canvas-runtime'
import RuntimeInput from '@/app/components/canvas-runtime/runtime-input'
import { useRuntimeStore } from '@/app/components/canvas-runtime/runtime-store'
import { useParams, useRouter } from '@/next/navigation'
import { fetchInstalledAppList } from '@/service/explore'

type InstalledAppListResp = {
  installed_apps: ExploreInstalledApp[]
}

/**
 * Canvas runtime page.
 *
 * Authorization model: this page itself only renders chrome. All data
 * requests (chatflow run, rerun, canvas CRUD) go through endpoints that
 * already enforce tenant + owner scope, so a forged appId in the URL
 * cannot leak data — it just produces 404s on every API call. The
 * `installed_app` lookup below is purely a UX guard so the user sees a
 * clean "无权访问该应用" instead of a wall of failed requests.
 */
const CanvasRuntimePage = () => {
  const params = useParams<{ appId: string }>()
  const router = useRouter()
  const appId = params?.appId
  const [authState, setAuthState] = useState<'checking' | 'ok' | 'forbidden'>(
    'checking',
  )

  const goBack = useCallback(() => {
    router.push('/creator')
  }, [router])

  // Hooks below must run on every render regardless of authState, so they
  // sit above the early returns. The submit handler synthesises a reset
  // event on the runtime store; real SSE dispatch lands in CR6.
  const applyEvent = useRuntimeStore(s => s.applyEvent)
  const handleSubmit = useCallback(
    (payload: { text: string, files: unknown[] }) => {
      applyEvent({
        type: 'workflow_started',
        workflowRunId: `pending-${Date.now()}`,
      })
      console.warn('[canvas-runtime] CR5 submit (no SSE wired yet)', payload)
    },
    [applyEvent],
  )

  useEffect(() => {
    if (!appId) {
      setAuthState('forbidden')
      return
    }
    let cancelled = false;
    (async () => {
      try {
        const resp = (await fetchInstalledAppList(
          null,
        )) as InstalledAppListResp
        const list = resp?.installed_apps ?? []
        // Match either installed_app.id or the underlying app.id — different
        // surfaces in the UI use different identifiers in the URL.
        const allowed = list.some(
          item => item.id === appId || item.app?.id === appId,
        )
        if (cancelled)
          return
        setAuthState(allowed ? 'ok' : 'forbidden')
      }
      catch {
        if (cancelled)
          return
        setAuthState('forbidden')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [appId])

  if (authState === 'checking') {
    return (
      <div className="flex h-full items-center justify-center text-text-tertiary">
        正在加载画布…
      </div>
    )
  }

  if (authState === 'forbidden') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-text-tertiary">
        <div className="system-md-medium text-text-primary">无权访问该应用</div>
        <div className="system-sm-regular">
          该应用未在你的工作区中安装，或已被移除。
        </div>
        <button
          type="button"
          onClick={goBack}
          className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-3 py-1.5 system-sm-medium text-text-secondary hover:bg-components-button-secondary-bg-hover"
        >
          返回创作中心
        </button>
      </div>
    )
  }

  // CR5 wires the bottom input as a CanvasRuntime child so it floats
  // above the ReactFlow surface without intercepting pan/zoom events.
  // CR6 will mount paused-node portals; CR7 wires onSave for the
  // toolbar's "保存为画布".
  return (
    <div className="flex h-full flex-col">
      <CanvasRuntime>
        <RuntimeInput onSubmit={handleSubmit} />
      </CanvasRuntime>
    </div>
  )
}

export default CanvasRuntimePage
