'use client'
/* eslint-disable react/set-state-in-effect -- single-shot auth probe; Suspense not warranted for CR3 shell */

import type { InstalledApp as ExploreInstalledApp } from '@/models/explore'
import { useCallback, useEffect, useState } from 'react'
import CanvasRuntime from '@/app/components/canvas-runtime'
import RuntimeInput from '@/app/components/canvas-runtime/runtime-input'
import { useRuntimeStore } from '@/app/components/canvas-runtime/runtime-store'
import SaveCanvasDialog from '@/app/components/canvas-runtime/save-canvas-dialog'
import { useParams, useRouter, useSearchParams } from '@/next/navigation'
import { runChatflowOnCanvas } from '@/service/canvas-runtime'
import { fetchInstalledAppList, fetchTrialAppParams } from '@/service/explore'
import { getUserCanvasSnapshot } from '@/service/user-canvases'

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
  const searchParams = useSearchParams()
  const appId = params?.appId
  const canvasIdParam = searchParams?.get('canvas_id') ?? null
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
  const resetRuntime = useRuntimeStore(s => s.reset)
  const [saveOpen, setSaveOpen] = useState(false)
  const handleOpenSave = useCallback(() => setSaveOpen(true), [])
  const handleCloseSave = useCallback(() => setSaveOpen(false), [])
  const [snapshotExpired, setSnapshotExpired] = useState(false)
  // Chatflow's file_upload + system_parameters merged into the shape
  // RuntimeInput → FileFromLinkOrLocal expects (`{...file_upload,
  // fileUploadConfig: system_parameters}`). useFile() inside the
  // uploader assumes this object exists and reads `.fileUploadConfig`,
  // so passing undefined crashes. Fetch + remember per-app.
  // eslint-disable-next-line ts/no-explicit-any
  const [fileConfig, setFileConfig] = useState<any>(null)

  // FIX4: when ?canvas_id=… is present, replay the saved snapshot
  // into the runtime store as a sequence of synthetic SSE events so
  // the user sees the same canvas state they saved earlier. Real chat
  // dispatch still works on top of the replayed canvas.
  // FIX9: surface an inline "snapshot expired" banner when the source
  // workflow_run has been GC'd (server returns expired:true with empty
  // nodes); skip the replay in that case.
  useEffect(() => {
    if (!canvasIdParam || authState !== 'ok')
      return
    let cancelled = false;
    (async () => {
      try {
        const snap = await getUserCanvasSnapshot(canvasIdParam)
        if (cancelled)
          return
        if (snap.expired) {
          // FIX12 + FIX14: reset the runtime store completely before
          // showing the banner. Use store.reset() rather than synthesising
          // workflow_started/finished events — those would leave
          // workflowRunId set and the toolbar's "保存为画布" button would
          // re-enable for a snapshot whose source_run is gone, then
          // createUserCanvas() would fail server-side.
          resetRuntime()
          setSnapshotExpired(true)
          return
        }
        setSnapshotExpired(false)
        applyEvent({
          type: 'workflow_started',
          workflowRunId: snap.canvas.source_run_id,
        })
        for (const node of snap.nodes) {
          applyEvent({
            type: 'node_started',
            nodeId: node.node_id,
            nodeType: node.node_type,
            title: node.title || node.node_id,
            inputs: node.inputs ?? undefined,
            predecessorNodeId: node.predecessor_node_id || undefined,
          })
          applyEvent({
            type: 'node_finished',
            nodeId: node.node_id,
            outputs: node.outputs ?? undefined,
            status: node.status === 'succeeded' ? 'succeeded' : 'failed',
            error: node.error ?? undefined,
          })
        }
        applyEvent({
          type: 'workflow_finished',
          workflowRunId: snap.canvas.source_run_id,
        })
      }
      catch (err) {
        console.warn('[canvas-runtime] failed to load saved canvas', err)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [applyEvent, authState, canvasIdParam, resetRuntime])
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

  // Fetch the chatflow's file_upload + system_parameters once auth is OK,
  // build the {fileUploadConfig} shape that FileFromLinkOrLocal needs.
  useEffect(() => {
    if (!appId || authState !== 'ok')
      return
    let cancelled = false;
    (async () => {
      try {
        // eslint-disable-next-line ts/no-explicit-any
        const params = (await fetchTrialAppParams(appId)) as any
        if (cancelled)
          return
        setFileConfig({
          ...(params?.file_upload ?? {}),
          fileUploadConfig: params?.system_parameters ?? {},
        })
      }
      catch (err) {
        console.warn('[canvas-runtime] failed to load app params', err)
        if (cancelled)
          return
        // Fall back to an empty-but-shape-correct object so the uploader
        // doesn't crash; the file-size limits will resolve to defaults.
        setFileConfig({ fileUploadConfig: {} })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [appId, authState])

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
      {snapshotExpired && (
        <div className="border-state-warning-border border-b bg-state-warning-hover px-4 py-2 system-xs-regular text-text-warning-secondary">
          该画布的运行数据已过期或被清理，无法重现节点。仍可在底部输入框开始一次新的运行。
        </div>
      )}
      <CanvasRuntime
        appId={appId!}
        onSave={handleOpenSave}
        saveDisabled={!workflowRunId}
      >
        <RuntimeInput onSubmit={handleSubmit} fileConfig={fileConfig} />
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
