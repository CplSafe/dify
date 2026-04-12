'use client'

/**
 * Creator global API Key management modal.
 *
 * Reuses Dify's existing SecretKeyModal UI patterns (same components, same layout)
 * but operates on the user-level /creator/api-key endpoint instead of per-app keys.
 */

import { PlusIcon, XMarkIcon } from '@heroicons/react/20/solid'
import { RiDeleteBinLine, RiKey2Line } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import ActionButton from '@/app/components/base/action-button'
import Button from '@/app/components/base/button'
import Confirm from '@/app/components/base/confirm'
import CopyFeedback from '@/app/components/base/copy-feedback'
import Loading from '@/app/components/base/loading'
import Modal from '@/app/components/base/modal'
import { toast } from '@/app/components/base/ui/toast'
import InputCopy from '@/app/components/develop/secret-key/input-copy'
import s from '@/app/components/develop/secret-key/style.module.css'
import { del, get, post } from '@/service/base'

export type CreatorApiKey = {
  id: string
  token: string
  description: string | null
  last_used_at: string | null
  created_at: string
}

type Props = {
  isShow: boolean
  onClose: () => void
}

export function CreatorKeyModal({ isShow, onClose }: Props) {
  const [apiKey, setApiKey] = useState<CreatorApiKey | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [showConfirmRevoke, setShowConfirmRevoke] = useState(false)
  const [showNewKey, setShowNewKey] = useState(false)

  const loadKey = useCallback(() => {
    setLoading(true)
    get<{ api_key: CreatorApiKey | null }>('/creator/api-key')
      .then(res => setApiKey(res.api_key))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (isShow)
      loadKey()
  }, [isShow, loadKey])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const res = await post<{ api_key: CreatorApiKey }>('/creator/api-key', { body: {} })
      setApiKey(res.api_key)
      setShowNewKey(true)
    }
    catch {
      toast.error('生成失败，请重试')
    }
    finally {
      setGenerating(false)
    }
  }

  const handleRevoke = async () => {
    try {
      await del('/creator/api-key')
      setApiKey(null)
      setShowConfirmRevoke(false)
      toast.success('API Key 已撤销')
    }
    catch {
      toast.error('撤销失败，请重试')
    }
  }

  const formatDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '从未'

  return (
    <>
      <Modal
        isShow={isShow}
        onClose={onClose}
        title="Creator API Key"
        className={`${s.customModal} flex flex-col px-8`}
      >
        <div className="-mr-2 -mt-6 mb-4 flex justify-end">
          <XMarkIcon className="h-6 w-6 cursor-pointer text-text-tertiary" onClick={onClose} />
        </div>
        <p className="mt-1 shrink-0 text-[13px] font-normal leading-5 text-text-tertiary">
          这是您的全局 Creator API Key，可用于调用创作者平台上所有已发布应用，无需为每个应用单独申请密钥。
        </p>

        {loading && <div className="mt-4"><Loading /></div>}

        {!loading && apiKey && (
          <div className="mt-4 flex grow flex-col overflow-hidden">
            <div className="flex h-9 shrink-0 items-center border-b border-divider-regular text-xs font-semibold text-text-tertiary">
              <div className="w-64 shrink-0 px-3">密钥</div>
              <div className="w-[200px] shrink-0 px-3">创建时间</div>
              <div className="w-[200px] shrink-0 px-3">最后使用</div>
              <div className="grow px-3" />
            </div>
            <div className="flex h-9 items-center border-b border-divider-regular text-sm font-normal text-text-secondary">
              <div className="w-64 shrink-0 truncate px-3 font-mono">
                {`${apiKey.token.slice(0, 6)}...${apiKey.token.slice(-20)}`}
              </div>
              <div className="w-[200px] shrink-0 truncate px-3">{formatDate(apiKey.created_at)}</div>
              <div className="w-[200px] shrink-0 truncate px-3">{formatDate(apiKey.last_used_at)}</div>
              <div className="flex grow space-x-2 px-3">
                <CopyFeedback content={apiKey.token} />
                <ActionButton onClick={() => setShowConfirmRevoke(true)}>
                  <RiDeleteBinLine className="h-4 w-4" />
                </ActionButton>
              </div>
            </div>
          </div>
        )}

        {!loading && (
          <div className="flex">
            <Button
              className={`mt-4 flex shrink-0 ${s.autoWidth}`}
              onClick={handleGenerate}
              disabled={generating}
            >
              <PlusIcon className="mr-1 flex h-4 w-4 shrink-0" />
              <div className="text-xs font-medium text-text-secondary">
                {apiKey ? '重新生成' : '生成 API Key'}
              </div>
            </Button>
          </div>
        )}
      </Modal>

      {/* Show newly generated key — same as SecretKeyGenerateModal */}
      <Modal
        isShow={showNewKey}
        onClose={() => setShowNewKey(false)}
        title="Creator API Key"
        className="px-8"
      >
        <div className="-mr-2 -mt-6 mb-4 flex justify-end">
          <XMarkIcon className="h-6 w-6 cursor-pointer text-text-tertiary" onClick={() => setShowNewKey(false)} />
        </div>
        <p className="mt-1 text-[13px] font-normal leading-5 text-text-tertiary">
          请妥善保管，此密钥只显示一次。
        </p>
        <div className="my-4">
          <InputCopy className="w-full" value={apiKey?.token} />
        </div>
        <div className="my-4 flex justify-end">
          <Button className={`shrink-0 ${s.w64}`} onClick={() => setShowNewKey(false)}>
            <span className="text-xs font-medium text-text-secondary">确定</span>
          </Button>
        </div>
      </Modal>

      {showConfirmRevoke && (
        <Confirm
          title="撤销 API Key"
          content="确定撤销？所有使用该密钥的调用将立即失败，此操作不可恢复。"
          isShow={showConfirmRevoke}
          onConfirm={handleRevoke}
          onCancel={() => setShowConfirmRevoke(false)}
        />
      )}
    </>
  )
}

/** Button that opens the CreatorKeyModal — same visual style as SecretKeyButton */
export function CreatorKeyButton({ className }: { className?: string }) {
  const [isVisible, setVisible] = useState(false)
  return (
    <>
      <Button
        className={`px-3 ${className}`}
        onClick={() => setVisible(true)}
        size="small"
        variant="ghost"
      >
        <RiKey2Line className="h-3.5 w-3.5 text-text-tertiary" />
        <span className="system-xs-medium px-[3px] text-text-tertiary">API Key</span>
      </Button>
      <CreatorKeyModal isShow={isVisible} onClose={() => setVisible(false)} />
    </>
  )
}
