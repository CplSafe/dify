'use client'

import { RiArrowDownLine, RiArrowUpLine, RiLoader4Line } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { toast } from '@/app/components/base/ui/toast'
import { useAppContext } from '@/context/app-context'
import { get, post } from '@/service/base'
import { cn } from '@/utils/classnames'

type Balance = {
  account_id: string
  balance: string
  currency: string
  is_sufficient: boolean
}

type BillingRecord = {
  id: string
  amount: string
  record_type: 'topup' | 'consume'
  description: string
  created_at: string
}

type AdminBalance = {
  account_id: string
  account_name: string
  account_email: string
  balance: string
  currency: string
  is_sufficient: boolean
}

const sectionTitleClass = 'system-sm-semibold text-text-secondary'
const sectionDescClass = 'mt-1 body-xs-regular text-text-tertiary'

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function BalanceTab() {
  const { isSystemAdmin } = useAppContext()

  const [balance, setBalance] = useState<Balance | null>(null)
  const [records, setRecords] = useState<BillingRecord[]>([])
  const [adminBalances, setAdminBalances] = useState<AdminBalance[]>([])
  const [loading, setLoading] = useState(true)

  // Topup form state
  const [topupAccountId, setTopupAccountId] = useState('')
  const [topupAmount, setTopupAmount] = useState('')
  const [topupNote, setTopupNote] = useState('')
  const [saving, setSaving] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [bal, recs] = await Promise.all([
        get<Balance>('/creator/balance'),
        get<{ data: BillingRecord[] }>('/creator/billing/records'),
      ])
      setBalance(bal)
      setRecords(recs.data || [])

      if (isSystemAdmin) {
        const adminBal = await get<{ data: AdminBalance[] }>('/creator/admin/balances')
        setAdminBalances(adminBal.data || [])
      }
    }
    catch {}
    finally {
      setLoading(false)
    }
  }, [isSystemAdmin])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleTopup = async () => {
    if (!topupAccountId || !topupAmount)
      return
    const amount = Number(topupAmount)
    if (!amount || amount <= 0) {
      toast.error('请输入有效金额')
      return
    }
    setSaving(true)
    try {
      await post('/creator/admin/topup', {
        body: { account_id: topupAccountId, amount, description: topupNote },
      })
      toast.success('充值成功')
      setTopupAmount('')
      setTopupNote('')
      await loadData()
    }
    catch {
      toast.error('充值失败，请稍后重试')
    }
    finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-8 pb-3 pt-2">
      {/* My balance card — mirrors workspace header card in MembersPage */}
      {balance && (
        <div className="flex items-center gap-3 rounded-xl border-l-[0.5px] border-t-[0.5px] border-divider-subtle bg-linear-to-r from-background-gradient-bg-fill-chat-bg-2 to-background-gradient-bg-fill-chat-bg-1 p-3 pr-5">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-components-icon-bg-blue-solid">
            <span className="i-ri-wallet-3-fill h-6 w-6 text-white" />
          </div>
          <div className="grow">
            <div className="text-text-secondary system-md-semibold">我的余额</div>
            <div className="mt-0.5 text-text-tertiary system-xs-medium">
              <span className={cn(
                'text-2xl font-bold',
                balance.is_sufficient ? 'text-text-primary' : 'text-state-destructive-text',
              )}
              >
                {Number(balance.balance).toFixed(2)}
              </span>
              <span className="ml-1 text-sm">{balance.currency}</span>
            </div>
          </div>
          {!balance.is_sufficient && (
            <div className="shrink-0 rounded-lg bg-state-destructive-hover px-3 py-1.5 text-xs font-medium text-state-destructive-text">
              余额不足，请联系管理员充值
            </div>
          )}
        </div>
      )}

      {/* Admin: topup section */}
      {isSystemAdmin && (
        <div>
          <div className={sectionTitleClass}>用户充值</div>
          <div className={sectionDescClass}>为空间成员充值余额</div>
          <div className="mt-4 rounded-xl border border-divider-subtle p-5 space-y-4">
            <div>
              <div className="mb-1.5 text-xs font-medium text-text-tertiary">选择用户</div>
              <select
                value={topupAccountId}
                onChange={e => setTopupAccountId(e.target.value)}
                className="w-full rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
                <option value="">请选择用户...</option>
                {adminBalances.map(b => (
                  <option key={b.account_id} value={b.account_id}>
                    {b.account_name}
                    （
                    {b.account_email}
                    ）— 余额
                    {Number(b.balance).toFixed(2)}
                    {' '}
                    {b.currency}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <div className="mb-1.5 text-xs font-medium text-text-tertiary">充值金额</div>
                <Input
                  type="number"
                  value={topupAmount}
                  onChange={e => setTopupAmount(e.target.value)}
                  placeholder="输入金额"
                  min="0.01"
                  step="0.01"
                />
              </div>
              <div className="flex-1">
                <div className="mb-1.5 text-xs font-medium text-text-tertiary">备注（可选）</div>
                <Input
                  value={topupNote}
                  onChange={e => setTopupNote(e.target.value)}
                  placeholder="充值备注"
                />
              </div>
            </div>
            <div className="flex justify-end">
              <Button
                variant="primary"
                disabled={!topupAccountId || !topupAmount || saving}
                onClick={() => void handleTopup()}
              >
                {saving ? '充值中...' : '确认充值'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Admin: all balances table */}
      {isSystemAdmin && adminBalances.length > 0 && (
        <div>
          <div className={sectionTitleClass}>所有用户余额</div>
          <div className="mt-3 overflow-hidden rounded-xl border border-divider-subtle">
            <div className="flex items-center border-b border-divider-regular py-[7px]">
              <div className="grow px-4 text-text-tertiary system-xs-medium-uppercase">用户</div>
              <div className="w-[140px] shrink-0 px-4 text-text-tertiary system-xs-medium-uppercase">余额</div>
              <div className="w-[80px] shrink-0 px-4 text-text-tertiary system-xs-medium-uppercase">状态</div>
            </div>
            {adminBalances.map(b => (
              <div key={b.account_id} className="flex items-center border-b border-divider-subtle last:border-0">
                <div className="flex grow items-center gap-2.5 px-4 py-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-100 text-xs font-semibold text-primary-700">
                    {b.account_name?.charAt(0)?.toUpperCase() || 'U'}
                  </div>
                  <div>
                    <div className="text-text-secondary system-sm-medium">{b.account_name}</div>
                    <div className="text-text-tertiary system-xs-regular">{b.account_email}</div>
                  </div>
                </div>
                <div className="w-[140px] shrink-0 px-4 py-3 text-text-secondary system-sm-regular">
                  {Number(b.balance).toFixed(2)}
                  {' '}
                  {b.currency}
                </div>
                <div className="w-[80px] shrink-0 px-4 py-3">
                  <span className={cn(
                    'rounded-full px-2 py-0.5 text-xs font-medium',
                    b.is_sufficient
                      ? 'bg-state-success-hover text-state-success-text'
                      : 'bg-state-destructive-hover text-state-destructive-text',
                  )}
                  >
                    {b.is_sufficient ? '充足' : '不足'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Billing records */}
      <div>
        <div className={sectionTitleClass}>账单记录</div>
        <div className={sectionDescClass}>您的余额变动历史</div>
        <div className="mt-3">
          {records.length === 0
            ? (
                <div className="flex items-center justify-center rounded-xl border border-divider-subtle py-12 text-sm text-text-quaternary">
                  暂无账单记录
                </div>
              )
            : (
                <div className="overflow-hidden rounded-xl border border-divider-subtle">
                  <div className="flex items-center border-b border-divider-regular py-[7px]">
                    <div className="grow px-4 text-text-tertiary system-xs-medium-uppercase">描述</div>
                    <div className="w-[160px] shrink-0 px-4 text-text-tertiary system-xs-medium-uppercase">时间</div>
                    <div className="w-[100px] shrink-0 px-4 text-right text-text-tertiary system-xs-medium-uppercase">金额</div>
                  </div>
                  {records.map(r => (
                    <div key={r.id} className="flex items-center border-b border-divider-subtle last:border-0">
                      <div className="flex grow items-center gap-2.5 px-4 py-3">
                        <div className={cn(
                          'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                          r.record_type === 'topup'
                            ? 'bg-state-success-hover text-state-success-text'
                            : 'bg-state-destructive-hover text-state-destructive-text',
                        )}
                        >
                          {r.record_type === 'topup'
                            ? <RiArrowUpLine className="h-3.5 w-3.5" />
                            : <RiArrowDownLine className="h-3.5 w-3.5" />}
                        </div>
                        <span className="text-text-secondary system-sm-regular">
                          {r.description || (r.record_type === 'topup' ? '充值' : '消费')}
                        </span>
                      </div>
                      <div className="w-[160px] shrink-0 px-4 py-3 text-text-tertiary system-xs-regular">
                        {formatDate(r.created_at)}
                      </div>
                      <div className={cn(
                        'w-[100px] shrink-0 px-4 py-3 text-right system-sm-semibold',
                        r.record_type === 'topup' ? 'text-state-success-text' : 'text-state-destructive-text',
                      )}
                      >
                        {r.record_type === 'topup' ? '+' : '-'}
                        {Number(r.amount).toFixed(2)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
        </div>
      </div>
    </div>
  )
}
