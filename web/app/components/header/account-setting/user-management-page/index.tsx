'use client'

import { RiArrowDownSLine, RiArrowRightSLine, RiLoader4Line, RiWalletLine } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { toast } from '@/app/components/base/ui/toast'
import { get, post } from '@/service/base'
import { cn } from '@/utils/classnames'

type UserBalance = {
  account_id: string
  account_name: string
  account_email: string
  balance: string
  currency: string
  is_sufficient: boolean
  updated_at: string
}

type BillingRecord = {
  id: string
  account_id: string
  amount: string
  record_type: string
  description: string | null
  created_at: string
}

type ExpandedState = {
  [accountId: string]: {
    open: boolean
    records: BillingRecord[]
    loading: boolean
    total: number
    offset: number
  }
}

export default function UserManagementPage() {
  const [users, setUsers] = useState<UserBalance[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const limit = 20

  const [expanded, setExpanded] = useState<ExpandedState>({})

  // Topup state
  const [topupAccountId, setTopupAccountId] = useState('')
  const [topupAmount, setTopupAmount] = useState('')
  const [topupDesc, setTopupDesc] = useState('')
  const [topupLoading, setTopupLoading] = useState(false)

  const loadUsers = useCallback(async (off: number) => {
    setLoading(true)
    try {
      const resp = await get<{ data: UserBalance[], total: number }>('/creator/admin/balances', {
        params: { limit, offset: off },
      })
      setUsers(resp.data)
      setTotal(resp.total)
      setOffset(off)
    }
    catch {
      toast.error('加载用户列表失败')
    }
    finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUsers(0)
  }, [loadUsers])

  const toggleUser = async (accountId: string) => {
    const cur = expanded[accountId]
    if (cur?.open) {
      setExpanded(prev => ({ ...prev, [accountId]: { ...cur, open: false } }))
      return
    }

    if (cur?.records.length) {
      setExpanded(prev => ({ ...prev, [accountId]: { ...cur, open: true } }))
      return
    }

    setExpanded(prev => ({
      ...prev,
      [accountId]: { open: true, records: [], loading: true, total: 0, offset: 0 },
    }))

    try {
      const resp = await get<{ data: BillingRecord[], total: number }>('/creator/admin/billing/records', {
        params: { account_id: accountId, limit: 10, offset: 0 },
      })
      setExpanded(prev => ({
        ...prev,
        [accountId]: { open: true, records: resp.data, loading: false, total: resp.total, offset: 0 },
      }))
    }
    catch {
      setExpanded(prev => ({
        ...prev,
        [accountId]: { open: true, records: [], loading: false, total: 0, offset: 0 },
      }))
    }
  }

  const loadMoreRecords = async (accountId: string) => {
    const cur = expanded[accountId]
    if (!cur)
      return
    const nextOffset = cur.offset + 10
    try {
      const resp = await get<{ data: BillingRecord[], total: number }>('/creator/admin/billing/records', {
        params: { account_id: accountId, limit: 10, offset: nextOffset },
      })
      setExpanded(prev => ({
        ...prev,
        [accountId]: {
          ...cur,
          records: [...cur.records, ...resp.data],
          total: resp.total,
          offset: nextOffset,
        },
      }))
    }
    catch {
      toast.error('加载账单失败')
    }
  }

  const handleTopup = async () => {
    if (!topupAccountId || !topupAmount)
      return
    const amount = Number.parseFloat(topupAmount)
    if (isNaN(amount) || amount <= 0) {
      toast.error('请输入有效的金额')
      return
    }
    setTopupLoading(true)
    try {
      await post('/creator/admin/topup', {
        body: { account_id: topupAccountId, amount, description: topupDesc || '管理员充值' },
      })
      toast.success('充值成功')
      setTopupAmount('')
      setTopupDesc('')
      // Refresh list and expanded records
      loadUsers(offset)
      if (expanded[topupAccountId]) {
        setExpanded(prev => ({
          ...prev,
          [topupAccountId]: { open: false, records: [], loading: false, total: 0, offset: 0 },
        }))
      }
    }
    catch {
      toast.error('充值失败，请重试')
    }
    finally {
      setTopupLoading(false)
    }
  }

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString('zh-CN', { hour12: false })
    }
    catch {
      return iso
    }
  }

  const recordTypeLabel = (type: string) => {
    const map: Record<string, string> = {
      topup: '充值',
      deduction: '扣费',
      refund: '退款',
    }
    return map[type] ?? type
  }

  return (
    <div className="space-y-6">
      {/* Topup Panel */}
      <div className="rounded-xl border border-divider-regular bg-components-panel-bg p-4">
        <div className="mb-3 flex items-center gap-2">
          <RiWalletLine className="h-4 w-4 text-text-tertiary" />
          <span className="text-sm font-semibold text-text-primary">手动充值</span>
        </div>
        <div className="flex flex-wrap gap-3">
          <div className="flex-1 min-w-[180px]">
            <div className="mb-1 text-xs text-text-tertiary">账户 ID</div>
            <Input
              value={topupAccountId}
              onChange={e => setTopupAccountId(e.target.value)}
              placeholder="粘贴账户 ID"
            />
          </div>
          <div className="w-32">
            <div className="mb-1 text-xs text-text-tertiary">金额（元）</div>
            <Input
              type="number"
              value={topupAmount}
              onChange={e => setTopupAmount(e.target.value)}
              placeholder="0.00"
            />
          </div>
          <div className="flex-1 min-w-[160px]">
            <div className="mb-1 text-xs text-text-tertiary">备注（可选）</div>
            <Input
              value={topupDesc}
              onChange={e => setTopupDesc(e.target.value)}
              placeholder="充值说明"
            />
          </div>
          <div className="flex items-end">
            <Button
              variant="primary"
              disabled={!topupAccountId || !topupAmount || topupLoading}
              onClick={handleTopup}
            >
              {topupLoading ? <RiLoader4Line className="mr-1 h-4 w-4 animate-spin" /> : null}
              充值
            </Button>
          </div>
        </div>
      </div>

      {/* User List */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-semibold text-text-primary">
            用户列表
            <span className="ml-2 text-xs font-normal text-text-tertiary">
              共
              {total}
              {' '}
              人
            </span>
          </span>
        </div>

        {loading
          ? (
              <div className="flex items-center justify-center py-12">
                <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
              </div>
            )
          : (
              <div className="divide-y divide-divider-subtle rounded-xl border border-divider-regular overflow-hidden">
                {users.length === 0
                  ? (
                      <div className="py-12 text-center text-sm text-text-tertiary">暂无用户</div>
                    )
                  : users.map(user => (
                      <div key={user.account_id}>
                        {/* User Row */}
                        <div
                          className="flex cursor-pointer items-center gap-4 px-4 py-3 hover:bg-state-base-hover transition-colors"
                          onClick={() => toggleUser(user.account_id)}
                        >
                          {/* Expand toggle */}
                          <span className="shrink-0 text-text-quaternary">
                            {expanded[user.account_id]?.open
                              ? <RiArrowDownSLine className="h-4 w-4" />
                              : <RiArrowRightSLine className="h-4 w-4" />}
                          </span>

                          {/* Avatar */}
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100 text-sm font-semibold text-primary-700">
                            {user.account_name?.charAt(0)?.toUpperCase() || 'U'}
                          </div>

                          {/* Name + email */}
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-medium text-text-primary">{user.account_name || '—'}</div>
                            <div className="truncate text-xs text-text-tertiary">{user.account_email}</div>
                          </div>

                          {/* Account ID (copyable) */}
                          <div
                            className="hidden min-w-[120px] max-w-[180px] truncate text-xs text-text-quaternary sm:block cursor-copy"
                            title={user.account_id}
                            onClick={(e) => {
                              e.stopPropagation()
                              navigator.clipboard.writeText(user.account_id)
                              toast.success('ID 已复制')
                            }}
                          >
                            {user.account_id}
                          </div>

                          {/* Balance */}
                          <div className={cn(
                            'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium',
                            user.is_sufficient
                              ? 'bg-state-success-hover text-state-success-text'
                              : 'bg-state-destructive-hover text-state-destructive-text',
                          )}
                          >
                            {Number(user.balance).toFixed(2)}
                            {' '}
                            {user.currency}
                          </div>

                          {/* Updated at */}
                          <div className="hidden shrink-0 text-xs text-text-quaternary sm:block">
                            {formatDate(user.updated_at)}
                          </div>
                        </div>

                        {/* Expanded billing records */}
                        {expanded[user.account_id]?.open && (
                          <div className="bg-background-section-burn px-12 py-3">
                            {expanded[user.account_id].loading
                              ? (
                                  <div className="flex items-center gap-2 py-4 text-sm text-text-tertiary">
                                    <RiLoader4Line className="h-4 w-4 animate-spin" />
                                    加载账单中…
                                  </div>
                                )
                              : expanded[user.account_id].records.length === 0
                                ? (
                                    <div className="py-4 text-sm text-text-tertiary">暂无账单记录</div>
                                  )
                                : (
                                    <>
                                      <div className="mb-2 grid grid-cols-3 gap-2 text-xs font-medium text-text-tertiary">
                                        <span>时间</span>
                                        <span>类型</span>
                                        <span className="text-right">金额</span>
                                      </div>
                                      <div className="divide-y divide-divider-subtle">
                                        {expanded[user.account_id].records.map(rec => (
                                          <div key={rec.id} className="grid grid-cols-3 gap-2 py-2 text-xs">
                                            <span className="text-text-tertiary">{formatDate(rec.created_at)}</span>
                                            <span className={cn(
                                              'font-medium',
                                              rec.record_type === 'topup' || rec.record_type === 'refund'
                                                ? 'text-state-success-text'
                                                : 'text-state-destructive-text',
                                            )}
                                            >
                                              {recordTypeLabel(rec.record_type)}
                                              {rec.description
                                                ? (
                                                    <span className="ml-1 text-text-quaternary font-normal">
                                                      ·
                                                      {rec.description}
                                                    </span>
                                                  )
                                                : null}
                                            </span>
                                            <span className={cn(
                                              'text-right font-medium',
                                              rec.record_type === 'topup' || rec.record_type === 'refund'
                                                ? 'text-state-success-text'
                                                : 'text-state-destructive-text',
                                            )}
                                            >
                                              {rec.record_type === 'deduction' ? '-' : '+'}
                                              {Number(rec.amount).toFixed(4)}
                                            </span>
                                          </div>
                                        ))}
                                      </div>

                                      {expanded[user.account_id].records.length < expanded[user.account_id].total && (
                                        <button
                                          type="button"
                                          className="mt-2 text-xs text-components-button-primary-text hover:underline"
                                          onClick={() => loadMoreRecords(user.account_id)}
                                        >
                                          加载更多
                                        </button>
                                      )}
                                    </>
                                  )}

                            {/* Quick topup button for this user */}
                            <div className="mt-3 flex items-center gap-2 border-t border-divider-subtle pt-3">
                              <span className="text-xs text-text-tertiary">快速充值：</span>
                              <button
                                type="button"
                                className="text-xs text-components-button-primary-text hover:underline"
                                onClick={() => setTopupAccountId(user.account_id)}
                              >
                                填入 ID
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
              </div>
            )}

        {/* Pagination */}
        {!loading && total > limit && (
          <div className="mt-3 flex justify-center gap-2">
            <Button
              size="small"
              variant="secondary"
              disabled={offset === 0}
              onClick={() => loadUsers(Math.max(0, offset - limit))}
            >
              上一页
            </Button>
            <span className="flex items-center px-2 text-xs text-text-tertiary">
              {Math.floor(offset / limit) + 1}
              {' '}
              /
              {Math.ceil(total / limit)}
            </span>
            <Button
              size="small"
              variant="secondary"
              disabled={offset + limit >= total}
              onClick={() => loadUsers(offset + limit)}
            >
              下一页
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
