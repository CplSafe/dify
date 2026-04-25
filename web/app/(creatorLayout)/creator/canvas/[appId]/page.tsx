'use client'
/* eslint-disable react/set-state-in-effect -- single-shot auth probe; Suspense not warranted for CR3 shell */

import type { InstalledApp as ExploreInstalledApp } from '@/models/explore'
import { useCallback, useEffect, useState } from 'react'
import CanvasRuntime from '@/app/components/canvas-runtime'
import RuntimeInput from '@/app/components/canvas-runtime/runtime-input'
import { useRuntimeStore } from '@/app/components/canvas-runtime/runtime-store'
import SaveCanvasDialog from '@/app/components/canvas-runtime/save-canvas-dialog'
import { useParams, useRouter } from '@/next/navigation'
import { runChatflowOnCanvas } from '@/service/canvas-runtime'
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
  // sit above the early returns. CR6 wires the actual chatflow SSE:
  // run → events → store; pause + resume rides on the existing CR1
  // backend infrastructure.
  const applyEvent = useRuntimeStore(s => s.applyEvent)
  const setMessageId = useRuntimeStore(s => s.setMessageId)
  const workflowRunId = useRuntimeStore(s => s.workflowRunId)
  const [saveOpen, setSaveOpen] = useState(false)
  const handleOpenSave = useCallback(() => setSaveOpen(true), [])
  const handleCloseSave = useCallback(() => setSaveOpen(false), [])
  const handleSubmit = useCallback(
    (payload: { text: string, files: unknown[] }) => {
      if (!appId)
        return
      // Reset the canvas before each new run.
      applyEvent({
        type: 'workflow_started',
        workflowRunId: `pending-${Date.now()}`,
      })
      setMessageId(null)
      runChatflowOnCanvas(
        appId,
        {
          query: payload.text,
          // Inputs are empty for canvas runtime today — start-node vars
          // are set at chatflow author time. CR5+ will surface required
          // inputs into the bottom dock when there are any.
          inputs: {},
          files: payload.files,
        },
        {
          // Required IOnData; we don't need streaming text inside the
          // canvas runtime so just discard it.
          onData: () => {},
          onCompleted: () => {},
          onError: (err) => {
            console.error('[canvas-runtime] chatflow error', err)
          },
          onWorkflowStarted: (resp) => {
            applyEvent({
              type: 'workflow_started',
              workflowRunId: resp.workflow_run_id,
            })
            if (resp.message_id)
              setMessageId(resp.message_id)
          },
          onNodeStarted: (resp) => {
            const data = resp.data
            applyEvent({
              type: 'node_started',
              nodeId: data.node_id,
              nodeType: data.node_type as string,
              title: data.title,
              inputs: data.inputs as Record<string, unknown>,
              predecessorNodeId: data.predecessor_node_id || undefined,
            })
          },
          onNodeFinished: (resp) => {
            const data = resp.data
            applyEvent({
              type: 'node_finished',
              nodeId: data.node_id,
              outputs: data.outputs,
              status: data.status === 'succeeded' ? 'succeeded' : 'failed',
              error: data.error || undefined,
            })
          },
          onWorkflowPaused: (resp) => {
            applyEvent({
              type: 'workflow_paused',
              pausedNodeIds: resp.data.paused_nodes ?? [],
              // Reasons can arrive as either strings or {reason: string}
              // objects depending on the backend payload version; coerce
              // to strings so the parser only needs to handle one shape.
              reasons: (resp.data.reasons ?? []).map((r: unknown) =>
                typeof r === 'string'
                  ? r
                  : ((r as { reason?: string })?.reason ?? ''),
              ),
            })
          },
          onWorkflowFinished: (resp) => {
            applyEvent({
              type: 'workflow_finished',
              workflowRunId: resp.workflow_run_id,
            })
          },
        },
      )
    },
    [appId, applyEvent, setMessageId],
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
  // CR7 surfaces the toolbar's "保存为画布" — the dialog opens, calls
  // POST /creator/canvases (which already validates source_run_id ↔ app
  // server-side) and on success the user can find the saved canvas in
  // /creator/canvas. We pass through the live workflowRunId from the
  // store; the toolbar disables itself when there's nothing to save.
  return (
    <div className="flex h-full flex-col">
      <CanvasRuntime
        appId={appId!}
        onSave={handleOpenSave}
        saveDisabled={!workflowRunId}
      >
        <RuntimeInput onSubmit={handleSubmit} />
      </CanvasRuntime>
      <SaveCanvasDialog
        open={saveOpen}
        appId={appId!}
        sourceRunId={workflowRunId}
        onClose={handleCloseSave}
      />
    </div>
  )
}

export default CanvasRuntimePage
