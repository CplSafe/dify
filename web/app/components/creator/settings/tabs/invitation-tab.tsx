'use client'

import { useCallback, useEffect, useState } from 'react'
import { RiAddLine, RiDeleteBinLine, RiFileCopyLine, RiLoader4Line } from '@remixicon/react'
import Button from '@/app/components/base/button'
import { toast } from '@/app/components/base/ui/toast'
import { del, get, post } from '@/service/base'

type Invitation = {
  id: string
  invite_code: string
  inviter_account_id: string
  invitee_account_id: string | null
  invitee_name?: string
  invitee_email?: string
  status: string
  created_at: string
  used_at: string | null
}

export default function InvitationTab() {
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)

  const loadInvitations = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await get<{ data: Invitation[] }>('/creator/invitations')
      setInvitations(resp.data || [])
    }
    catch {
      toast.error('加载邀请列表失败')
    }
    finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadInvitations()
  }, [loadInvitations])

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await post<Invitation>('/creator/invitations', { body: {} })
      toast.success('邀请码已生成')
      loadInvitations()
    }
    catch {
      toast.error('生成失败')
    }
    finally {
      setGenerating(false)
    }
  }

  const handleRevoke = async (id: string) => {
    try {
      await del(`/creator/invitations/${id}`)
      toast.success('已撤销')
      loadInvitations()
    }
    catch {
      toast.error('撤销失败')
    }
  }

  const copyInviteLink = (code: string) => {
    const link = `${window.location.origin}/signin?invite_code=${code}`
    navigator.clipboard.writeText(link)
    toast.success('邀请链接已复制')
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString('zh-CN', { hour12: false })

  const STATUS_MAP: Record<string, { label: string; color: string }> = {
    pending: { label: '待使用', color: 'bg-state-warning-hover text-state-warning-text' },
    used: { label: '已使用', color: 'bg-state-success-hover text-state-success-text' },
    revoked: { label: '已撤销', color: 'bg-gray-100 text-gray-500' },
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-text-primary">邀请管理</div>
          <div className="mt-1 text-xs text-text-tertiary">
            生成邀请码分享给下级用户，注册后自动绑定上下级关系，下级用户的消耗将产生返点收入。
          </div>
        </div>
        <Button variant="primary" size="small" disabled={generating} onClick={handleGenerate}>
          {generating
            ? <RiLoader4Line className="mr-1 h-3.5 w-3.5 animate-spin" />
            : <RiAddLine className="mr-1 h-3.5 w-3.5" />}
          生成邀请码
        </Button>
      </div>

      {/* List */}
      {loading
        ? (
            <div className="flex items-center justify-center py-12">
              <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
            </div>
          )
        : invitations.length === 0
          ? (
              <div className="rounded-xl border border-dashed border-divider-regular p-8 text-center">
                <div className="text-text-tertiary">还没有邀请码</div>
                <div className="mt-1 text-xs text-text-quaternary">点击上方按钮生成邀请码，分享给下级用户</div>
              </div>
            )
          : (
              <div className="divide-y divide-divider-subtle rounded-xl border border-divider-regular overflow-hidden">
                {invitations.map(inv => {
                  const status = STATUS_MAP[inv.status] || STATUS_MAP.pending
                  return (
                    <div key={inv.id} className="flex items-center gap-4 px-4 py-3">
                      {/* Code */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <code className="font-mono text-sm font-medium text-text-primary">{inv.invite_code}</code>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${status.color}`}>
                            {status.label}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-text-quaternary">
                          创建于 {formatDate(inv.created_at)}
                          {inv.invitee_name && (
                            <span className="ml-2">
                              → <span className="text-text-secondary">{inv.invitee_name}</span>
                              <span className="ml-1 text-text-quaternary">({inv.invitee_email})</span>
                            </span>
                          )}
                          {inv.used_at && (
                            <span className="ml-2">绑定于 {formatDate(inv.used_at)}</span>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex shrink-0 items-center gap-1">
                        {inv.status === 'pending' && (
                          <>
                            <button
                              type="button"
                              onClick={() => copyInviteLink(inv.invite_code)}
                              className="rounded-md p-1.5 text-text-quaternary hover:bg-state-base-hover hover:text-text-secondary"
                              title="复制邀请链接"
                            >
                              <RiFileCopyLine className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleRevoke(inv.id)}
                              className="rounded-md p-1.5 text-text-quaternary hover:bg-state-destructive-hover hover:text-state-destructive-text"
                              title="撤销"
                            >
                              <RiDeleteBinLine className="h-4 w-4" />
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
    </div>
  )
}
