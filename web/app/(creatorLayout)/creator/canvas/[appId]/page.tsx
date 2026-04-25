'use client'
/* eslint-disable react/set-state-in-effect -- single-shot auth probe; Suspense not warranted for CR3 shell */

import type { StartVarValues } from '@/app/components/canvas-runtime/start-vars-helpers'
import type { InstalledApp as ExploreInstalledApp } from '@/models/explore'
import type { UserInputFormItem } from '@/types/app'
import { useCallback, useEffect, useState } from 'react'
import CanvasRuntime from '@/app/components/canvas-runtime'
import RuntimeInput from '@/app/components/canvas-runtime/runtime-input'
import RuntimeStartVars from '@/app/components/canvas-runtime/runtime-start-vars'
import { useRuntimeStore } from '@/app/components/canvas-runtime/runtime-store'
import SaveCanvasDialog from '@/app/components/canvas-runtime/save-canvas-dialog'
import { buildDefaultStartVars } from '@/app/components/canvas-runtime/start-vars-helpers'
import TopupModal from '@/app/components/creator/wallet/topup-modal'
import { useParams, useRouter, useSearchParams } from '@/next/navigation'
import {
  fetchCanvasAppParameters,
  runChatflowOnCanvas,
} from '@/service/canvas-runtime'
import { fetchInstalledAppList } from '@/service/explore'
import { getUserCanvasSnapshot } from '@/service/user-canvases'

type InstalledAppListResp = {
  installed_apps: ExploreInstalledApp[]
}

// Parse a system message and turn `[label](url)` markdown-style links
// into clickable spans. When the URL points at the balance / topup page
// we swap the link out for a "充值" button that opens TopupModal in
// place — keeps the user on the canvas instead of losing their state.
function renderSystemMessage(text: string, openTopup: () => void) {
  const parts: Array<string | { label: string, href: string }> = []
  const linkRe = /\[([^\]]+)\]\(([^)]+)\)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  // eslint-disable-next-line no-cond-assign
  while ((match = linkRe.exec(text)) !== null) {
    if (match.index > lastIndex)
      parts.push(text.slice(lastIndex, match.index))
    parts.push({ label: match[1], href: match[2] })
    lastIndex = linkRe.lastIndex
  }
  if (lastIndex < text.length)
    parts.push(text.slice(lastIndex))

  return parts.map((part, i) => {
    if (typeof part === 'string')
      return <span key={i}>{part}</span>
    const isBalance
      = part.href.includes('/balance')
        || part.href.includes('/wallet')
        || part.href.includes('/topup')
    if (isBalance) {
      return (
        <button
          key={i}
          type="button"
          onClick={openTopup}
          className="inline-flex items-center rounded-md bg-components-button-primary-bg px-2 py-0.5 system-xs-medium text-text-primary-on-surface hover:bg-components-button-primary-bg-hover"
        >
          点击「充值」
        </button>
      )
    }
    return (
      <a
        key={i}
        href={part.href}
        target="_blank"
        rel="noreferrer"
        className="text-text-accent underline"
      >
        {part.label}
      </a>
    )
  })
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
  // The URL slug can be either app_id (canonical) or installed_app_id.
  // Resolve both during the auth probe:
  //   - installedAppId → for /installed-apps/<id>/chat-messages and
  //     /installed-apps/<id>/parameters (creator-allowed routes).
  //   - resolvedAppId → for /apps/<app_id>/messages/.../resume-from
  //     (the rerun endpoints — admin-only today, see __init__.py).
  const [installedAppId, setInstalledAppId] = useState<string | null>(null)
  const [resolvedAppId, setResolvedAppId] = useState<string | null>(null)

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
  // System message banner can carry a [充值] link from balance-check
  // middleware. Detect it and surface as an inline TopupModal trigger
  // instead of routing the user to a different page.
  const [topupOpen, setTopupOpen] = useState(false)
  // Plain chatflow message answer (event: message). Surfaced as a
  // banner above the canvas so users see middleware bailouts (balance
  // checks, gating, etc.) and ad-hoc LLM replies even when no workflow
  // node ever fires.
  const messageAnswer = useRuntimeStore(s => s.messageAnswer)
  const messageEnded = useRuntimeStore(s => s.messageEnded)
  // Chatflow's file_upload + system_parameters merged into the shape
  // RuntimeInput → FileFromLinkOrLocal expects (`{...file_upload,
  // fileUploadConfig: system_parameters}`). useFile() inside the
  // uploader assumes this object exists and reads `.fileUploadConfig`,
  // so passing undefined crashes. Fetch + remember per-app.
  // eslint-disable-next-line ts/no-explicit-any
  const [fileConfig, setFileConfig] = useState<any>(null)
  // chatflow start-node user_input_form (industry / ratio / …). The
  // engine rejects the run with "<var> is required in input form" when
  // any required field is missing, so we render these inline above the
  // bottom textarea and merge into `inputs` on submit.
  const [startVarsForm, setStartVarsForm] = useState<UserInputFormItem[]>([])
  const [startVarValues, setStartVarValues] = useState<StartVarValues>({})

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
      if (!installedAppId)
        return
      // Required-field check for start vars. The engine would otherwise
      // 500 with "<var> is required in input form" before any node runs.
      const missing: { variable: string, label: string }[] = []
      for (const raw of startVarsForm) {
        const f
          = 'text-input' in raw
            ? raw['text-input']
            : 'paragraph' in raw
              ? raw.paragraph
              : 'select' in raw
                ? raw.select
                : null
        if (!f || !f.required)
          continue
        if (!(startVarValues[f.variable] ?? '').trim())
          missing.push({ variable: f.variable, label: f.label || f.variable })
      }
      if (missing.length > 0) {
        applyEvent({
          type: 'message',
          mode: 'replace',
          text: `请先填写必填项：${missing.map(f => f.label || f.variable).join('、')}`,
        })
        applyEvent({ type: 'message_end' })
        return
      }
      // Reset the canvas before each new run.
      applyEvent({
        type: 'workflow_started',
        workflowRunId: `pending-${Date.now()}`,
      })
      setMessageId(null)
      runChatflowOnCanvas(
        installedAppId,
        {
          query: payload.text,
          inputs: startVarValues,
          files: payload.files,
        },
        {
          // chatflow `event: message` chunks. Could be an LLM answer or
          // a middleware bailout (e.g. balance check returning 余额不足).
          // Either way we want it on screen, so push into the store as
          // an append-mode message event.
          onData: (chunk) => {
            applyEvent({ type: 'message', text: chunk, mode: 'append' })
          },
          onMessageEnd: () => {
            applyEvent({ type: 'message_end' })
          },
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
    [installedAppId, applyEvent, setMessageId, startVarsForm, startVarValues],
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
        // surfaces in the UI use different identifiers in the URL. Cache
        // the resolved installed_app.id so SSE / parameters calls have it.
        const matched = list.find(
          item => item.id === appId || item.app?.id === appId,
        )
        if (cancelled)
          return
        if (matched) {
          setInstalledAppId(matched.id)
          setResolvedAppId(matched.app?.id ?? null)
          setAuthState('ok')
        }
        else {
          setInstalledAppId(null)
          setResolvedAppId(null)
          setAuthState('forbidden')
        }
      }
      catch {
        if (cancelled)
          return
        setInstalledAppId(null)
        setResolvedAppId(null)
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
    if (!installedAppId || authState !== 'ok')
      return
    let cancelled = false;
    (async () => {
      try {
        const params = (await fetchCanvasAppParameters(installedAppId)) as {
          file_upload?: Record<string, unknown>
          system_parameters?: Record<string, unknown>
          user_input_form?: UserInputFormItem[]
        }
        if (cancelled)
          return
        setFileConfig({
          ...(params?.file_upload ?? {}),
          fileUploadConfig: params?.system_parameters ?? {},
        })
        const form = params?.user_input_form ?? []
        setStartVarsForm(form)
        setStartVarValues(buildDefaultStartVars(form))
      }
      catch (err) {
        console.warn('[canvas-runtime] failed to load app params', err)
        if (cancelled)
          return
        // Fall back to an empty-but-shape-correct object so the uploader
        // doesn't crash; the file-size limits will resolve to defaults.
        setFileConfig({ fileUploadConfig: {} })
        setStartVarsForm([])
        setStartVarValues({})
      }
    })()
    return () => {
      cancelled = true
    }
  }, [installedAppId, authState])

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
      {messageAnswer && (
        <div className="border-b border-components-panel-border bg-components-panel-bg px-4 py-3">
          <div className="mb-1 system-2xs-medium-uppercase text-text-tertiary">
            来自系统的消息
            {!messageEnded && '（接收中…）'}
          </div>
          <div className="system-sm-regular whitespace-pre-wrap text-text-primary">
            {renderSystemMessage(messageAnswer, () => setTopupOpen(true))}
          </div>
        </div>
      )}
      <CanvasRuntime
        appId={resolvedAppId ?? appId!}
        onSave={handleOpenSave}
        saveDisabled={!workflowRunId}
      >
        <RuntimeInput
          onSubmit={handleSubmit}
          fileConfig={fileConfig}
          startSlot={(
            <RuntimeStartVars
              form={startVarsForm}
              values={startVarValues}
              onChange={setStartVarValues}
            />
          )}
        />
      </CanvasRuntime>
      <SaveCanvasDialog
        open={saveOpen}
        appId={resolvedAppId ?? appId!}
        sourceRunId={workflowRunId}
        onClose={handleCloseSave}
      />
      <TopupModal open={topupOpen} onOpenChange={setTopupOpen} />
    </div>
  )
}

export default CanvasRuntimePage
