'use client'

import { RiArrowRightUpLine, RiEyeLine, RiEyeOffLine, RiLoader4Line, RiRefreshLine } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import Button from '@/app/components/base/button'
import { toast } from '@/app/components/base/ui/toast'
import { CreatorKeyModal } from '@/app/components/creator/creator-key-modal'
import { del, get, post } from '@/service/base'

type ApiKeyInfo = {
  id: string
  token: string
  description: string | null
  last_used_at: string | null
  created_at: string
}

type MarketplaceApp = {
  id: string
  app_id: string
  app_name: string
  app_mode: string
  icon_url: string | null
  app_icon: string
  app_icon_type: string
  app_icon_background: string
}

const MODE_LABEL: Record<string, string> = {
  'workflow': '工作流',
  'advanced-chat': '高级对话',
  'chat': '对话',
  'agent': 'Agent',
  'text-generation': '文本生成',
}

export default function ApiKeyTab() {
  const [apiKey, setApiKey] = useState<ApiKeyInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const [revealed, setRevealed] = useState(false)
  const [showConfirmRevoke, setShowConfirmRevoke] = useState(false)
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [apps, setApps] = useState<MarketplaceApp[]>([])

  const loadKey = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await get<{ api_key: ApiKeyInfo | null }>('/creator/api-key')
      setApiKey(resp.api_key)
    }
    catch {
      toast.error('加载 API Key 失败')
    }
    finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadKey()
    get<{ data: MarketplaceApp[] }>('/creator/marketplace/apps')
      .then(data => setApps(data.data || []))
      .catch(() => {})
  }, [loadKey])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const resp = await post<{ api_key: ApiKeyInfo }>('/creator/api-key', { body: {} })
      setApiKey(resp.api_key)
      setRevealed(true)
      toast.success(apiKey ? 'API Key 已重新生成' : 'API Key 已生成')
    }
    catch {
      toast.error('生成失败，请重试')
    }
    finally {
      setGenerating(false)
    }
  }

  const handleRevoke = async () => {
    setRevoking(true)
    try {
      await del('/creator/api-key')
      setApiKey(null)
      setRevealed(false)
      setShowConfirmRevoke(false)
      toast.success('API Key 已撤销')
    }
    catch {
      toast.error('撤销失败，请重试')
    }
    finally {
      setRevoking(false)
    }
  }

  const maskedToken = (token: string) =>
    revealed ? token : `${token.slice(0, 10)}${'•'.repeat(32)}`

  const formatDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '从未'

  return (
    <div className="space-y-6">
      {/* Key display / generate */}
      {loading
        ? (
            <div className="flex items-center justify-center py-12">
              <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
            </div>
          )
        : apiKey
          ? (
              <div className="rounded-xl border border-divider-regular bg-components-panel-bg p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-semibold text-text-primary">API Key</span>
                  <span className="rounded-full bg-state-success-hover px-2 py-0.5 text-xs text-state-success-text">有效</span>
                </div>

                <div className="mb-3 flex items-center gap-2 rounded-lg border border-divider-subtle bg-background-default px-3 py-2">
                  <code className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-sm text-text-secondary">
                    {maskedToken(apiKey.token)}
                  </code>
                  <button type="button" onClick={() => setRevealed(v => !v)} className="shrink-0 text-text-quaternary hover:text-text-secondary">
                    {revealed ? <RiEyeOffLine className="h-4 w-4" /> : <RiEyeLine className="h-4 w-4" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => { navigator.clipboard.writeText(apiKey.token); toast.success('已复制') }}
                    className="shrink-0 text-text-quaternary hover:text-text-secondary"
                  >
                    <RiArrowRightUpLine className="h-4 w-4" />
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs text-text-tertiary">
                  <div>
                    <div className="text-text-quaternary">创建时间</div>
                    <div className="mt-0.5 text-text-secondary">{formatDate(apiKey.created_at)}</div>
                  </div>
                  <div>
                    <div className="text-text-quaternary">最后使用</div>
                    <div className="mt-0.5 text-text-secondary">{formatDate(apiKey.last_used_at)}</div>
                  </div>
                </div>

                <div className="mt-4 flex items-center gap-3 border-t border-divider-subtle pt-4">
                  <Button variant="secondary" size="small" disabled={generating} onClick={handleGenerate}>
                    {generating ? <RiLoader4Line className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RiRefreshLine className="mr-1 h-3.5 w-3.5" />}
                    重新生成
                  </Button>
                  <button type="button" className="text-xs text-state-destructive-text hover:underline" onClick={() => setShowConfirmRevoke(true)}>
                    撤销密钥
                  </button>
                </div>

                {showConfirmRevoke && (
                  <div className="mt-3 rounded-lg border border-state-destructive-border bg-state-destructive-hover p-3">
                    <p className="mb-2 text-xs text-state-destructive-text">确定撤销？所有使用该密钥的调用将立即失败。</p>
                    <div className="flex gap-2">
                      <Button variant="warning" size="small" disabled={revoking} onClick={handleRevoke}>
                        {revoking && <RiLoader4Line className="mr-1 h-3.5 w-3.5 animate-spin" />}
                        确认撤销
                      </Button>
                      <Button variant="secondary" size="small" onClick={() => setShowConfirmRevoke(false)}>取消</Button>
                    </div>
                  </div>
                )}
              </div>
            )
          : (
              <div className="rounded-xl border border-dashed border-divider-regular p-8 text-center">
                <div className="mb-3 text-text-tertiary">还没有 API Key</div>
                <p className="mb-4 text-sm text-text-quaternary">生成后可通过 API 调用创作者平台上发布的应用</p>
                <Button variant="primary" disabled={generating} onClick={() => setShowKeyModal(true)}>
                  生成 API Key
                </Button>
              </div>
            )}

      {/* App API docs links */}
      {apps.length > 0 && (
        <div>
          <div className="mb-3 text-sm font-semibold text-text-primary">应用接口文档</div>
          <p className="mb-3 text-xs text-text-tertiary">
            不同应用类型的调用方式不同（工作流、对话、Agent 等），点击查看各应用的详细接口文档和调试工具。
          </p>
          <div className="divide-y divide-divider-subtle rounded-xl border border-divider-regular overflow-hidden">
            {apps.map(app => (
              <a
                key={app.app_id}
                href={`/creator-docs/${app.app_id}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-3 px-4 py-3 hover:bg-state-base-hover transition-colors group"
              >
                <div
                  className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-lg text-base"
                  style={{ background: app.app_icon_type === 'image' ? undefined : (app.app_icon_background || '#E0E0FF') }}
                >
                  {app.app_icon_type === 'image' && app.icon_url
                    ? <img src={app.icon_url} alt={app.app_name} className="h-full w-full object-cover" />
                    : <span>{app.app_icon || '🤖'}</span>}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-text-primary">{app.app_name}</div>
                  <div className="text-xs text-text-quaternary">{MODE_LABEL[app.app_mode] ?? app.app_mode}</div>
                </div>

                <RiArrowRightUpLine className="h-4 w-4 shrink-0 text-text-quaternary opacity-0 transition-opacity group-hover:opacity-100" />
              </a>
            ))}
          </div>
          <p className="mt-2 text-xs text-text-quaternary">
            在接口文档页可查看调用示例、测试接口，并使用您的全局 API Key 替换页面中的 App 密钥。
          </p>
        </div>
      )}

      {/* Shared creator key modal — used when generating for the first time */}
      <CreatorKeyModal
        isShow={showKeyModal}
        onClose={() => {
          setShowKeyModal(false)
          loadKey()
        }}
      />
    </div>
  )
}
