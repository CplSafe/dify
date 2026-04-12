'use client'

import { RiAddLine, RiArrowDownLine, RiArrowUpLine } from '@remixicon/react'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useAppContext } from '@/context/app-context'

type Balance = {
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
  workflow_run_id: string | null
  amount: string
  currency: string
  record_type: string
  description: string | null
  created_at: string
}

export default function AdminBillingPage() {
  const { isSystemAdmin, isLoadingCurrentWorkspace } = useAppContext()
  const router = useRouter()
  const [balances, setBalances] = useState<Balance[]>([])
  const [records, setRecords] = useState<BillingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [topupForm, setTopupForm] = useState({ account_id: '', amount: '', description: '' })
  const [topupLoading, setTopupLoading] = useState(false)
  const [topupMessage, setTopupMessage] = useState('')
  const [activeTab, setActiveTab] = useState<'balances' | 'records'>('balances')

  useEffect(() => {
    if (!isLoadingCurrentWorkspace && !isSystemAdmin) {
      router.replace('/apps')
    }
  }, [isSystemAdmin, isLoadingCurrentWorkspace, router])

  useEffect(() => {
    if (!isSystemAdmin)
      return
    Promise.all([
      fetch('/console/api/creator/admin/balances').then(r => r.json()),
      fetch('/console/api/creator/admin/billing/records').then(r => r.json()),
    ]).then(([balanceData, recordData]) => {
      setBalances(balanceData.data || [])
      setRecords(recordData.data || [])
    }).catch(() => {}).finally(() => setLoading(false))
  }, [isSystemAdmin])

  const handleTopup = async () => {
    if (!topupForm.account_id || !topupForm.amount)
      return
    setTopupLoading(true)
    setTopupMessage('')
    try {
      const resp = await fetch('/console/api/creator/admin/topup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: topupForm.account_id,
          amount: Number.parseFloat(topupForm.amount),
          description: topupForm.description,
        }),
      })
      if (resp.ok) {
        setTopupMessage('充值成功！')
        setTopupForm({ account_id: '', amount: '', description: '' })
        // Refresh balances
        const data = await fetch('/console/api/creator/admin/balances').then(r => r.json())
        setBalances(data.data || [])
      }
      else {
        const err = await resp.json()
        setTopupMessage(`充值失败: ${err.message || '未知错误'}`)
      }
    }
    catch {
      setTopupMessage('请求失败，请重试')
    }
    finally {
      setTopupLoading(false)
    }
  }

  if (!isSystemAdmin && !isLoadingCurrentWorkspace)
    return null

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-divider-subtle px-8 py-6">
        <h1 className="text-2xl font-bold text-text-primary">账户余额管理</h1>
        <p className="mt-1 text-text-quaternary">查看所有用户余额，管理充值和账单记录</p>
      </div>

      <div className="flex-1 p-8 space-y-8">
        {/* Top-up form */}
        <div className="rounded-2xl border border-divider-subtle bg-background-default p-6">
          <h2 className="mb-4 flex items-center gap-2 font-semibold text-text-primary">
            <RiAddLine className="h-5 w-5 text-primary-600" />
            为用户充值
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">账户 ID</label>
              <input
                type="text"
                value={topupForm.account_id}
                onChange={e => setTopupForm(p => ({ ...p, account_id: e.target.value }))}
                placeholder="粘贴用户账户 ID"
                className="w-full rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-quaternary focus:border-primary-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">金额 (CNY)</label>
              <input
                type="number"
                min={0.01}
                step={0.01}
                value={topupForm.amount}
                onChange={e => setTopupForm(p => ({ ...p, amount: e.target.value }))}
                placeholder="0.00"
                className="w-full rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-quaternary focus:border-primary-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-text-secondary">备注</label>
              <input
                type="text"
                value={topupForm.description}
                onChange={e => setTopupForm(p => ({ ...p, description: e.target.value }))}
                placeholder="充值备注（可选）"
                className="w-full rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary outline-none placeholder:text-text-quaternary focus:border-primary-500"
              />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={handleTopup}
              disabled={topupLoading || !topupForm.account_id || !topupForm.amount}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {topupLoading ? '充值中...' : '立即充值'}
            </button>
            {topupMessage && (
              <span className={`text-sm ${topupMessage.includes('成功') ? 'text-green-600' : 'text-red-600'}`}>
                {topupMessage}
              </span>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-4 border-b border-divider-subtle">
          {(['balances', 'records'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-text-quaternary hover:text-text-secondary'
              }`}
            >
              {tab === 'balances' ? '用户余额' : '账单记录'}
            </button>
          ))}
        </div>

        {loading
          ? <div className="py-12 text-center text-text-quaternary">加载中...</div>
          : activeTab === 'balances'
            ? (
                <div className="overflow-hidden rounded-2xl border border-divider-subtle">
                  <table className="w-full text-sm">
                    <thead className="bg-background-default-dimm">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">用户</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">账户 ID</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">余额</th>
                        <th className="px-4 py-3 text-center font-medium text-text-secondary">状态</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-divider-subtle">
                      {balances.map(b => (
                        <tr key={b.account_id} className="hover:bg-background-default-dimm">
                          <td className="px-4 py-3">
                            <div className="font-medium text-text-primary">{b.account_name}</div>
                            <div className="text-xs text-text-quaternary">{b.account_email}</div>
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-text-quaternary">{b.account_id}</td>
                          <td className="px-4 py-3 text-right">
                            <span className={`font-semibold ${Number.parseFloat(b.balance) < 0 ? 'text-red-600' : 'text-text-primary'}`}>
                              ¥
                              {Number.parseFloat(b.balance).toFixed(2)}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${b.is_sufficient ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                              {b.is_sufficient ? '正常' : '欠费'}
                            </span>
                          </td>
                        </tr>
                      ))}
                      {balances.length === 0 && (
                        <tr>
                          <td colSpan={4} className="px-4 py-8 text-center text-text-quaternary">暂无用户余额记录</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )
            : (
                <div className="overflow-hidden rounded-2xl border border-divider-subtle">
                  <table className="w-full text-sm">
                    <thead className="bg-background-default-dimm">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">类型</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">账户 ID</th>
                        <th className="px-4 py-3 text-right font-medium text-text-secondary">金额</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">描述</th>
                        <th className="px-4 py-3 text-left font-medium text-text-secondary">时间</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-divider-subtle">
                      {records.map(r => (
                        <tr key={r.id} className="hover:bg-background-default-dimm">
                          <td className="px-4 py-3">
                            <span className={`flex items-center gap-1 w-fit rounded-full px-2 py-0.5 text-xs font-medium ${r.record_type === 'topup' ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>
                              {r.record_type === 'topup' ? <RiArrowUpLine className="h-3 w-3" /> : <RiArrowDownLine className="h-3 w-3" />}
                              {r.record_type === 'topup' ? '充值' : '扣费'}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-text-quaternary">{r.account_id}</td>
                          <td className="px-4 py-3 text-right font-semibold text-text-primary">
                            {r.record_type === 'topup' ? '+' : '-'}
                            ¥
                            {Number.parseFloat(r.amount).toFixed(4)}
                          </td>
                          <td className="px-4 py-3 text-text-secondary max-w-[200px] truncate">{r.description || '-'}</td>
                          <td className="px-4 py-3 text-xs text-text-quaternary">
                            {new Date(r.created_at).toLocaleString('zh-CN')}
                          </td>
                        </tr>
                      ))}
                      {records.length === 0 && (
                        <tr>
                          <td colSpan={5} className="px-4 py-8 text-center text-text-quaternary">暂无账单记录</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
      </div>
    </div>
  )
}
