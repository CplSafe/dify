'use client'

import { RiLoader4Line } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import { toast } from '@/app/components/base/ui/toast'
import { get } from '@/service/base'

type RebateRecord = {
  id: string
  inviter_account_id: string
  invitee_account_id: string
  invitee_name?: string
  settlement_date: string
  consumption_amount: string
  cost_amount: string
  rebate_amount: string
  rebate_rate: string
  cost_rate: string
  currency: string
  created_at: string
}

type RebateSummary = {
  total_rebate: string
  total_consumption: string
  invitee_count: number
  currency: string
}

export default function RebateTab() {
  const [records, setRecords] = useState<RebateRecord[]>([])
  const [summary, setSummary] = useState<RebateSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const perPage = 20

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [recordsResp, summaryResp] = await Promise.all([
        get<{ data: RebateRecord[], total: number }>(`/creator/rebate/records?page=${page}&per_page=${perPage}`),
        get<RebateSummary>('/creator/rebate/summary'),
      ])
      setRecords(recordsResp.data || [])
      setTotal(recordsResp.total || 0)
      setSummary(summaryResp)
    }
    catch {
      toast.error('加载返点记录失败')
    }
    finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    loadData()
  }, [loadData])

  const totalPages = Math.ceil(total / perPage)

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-xl border border-divider-regular bg-components-panel-bg p-4">
            <div className="text-xs text-text-quaternary">累计返点收入</div>
            <div className="mt-1 text-xl font-bold text-state-success-text">
              ¥
              {Number(summary.total_rebate).toFixed(2)}
            </div>
          </div>
          <div className="rounded-xl border border-divider-regular bg-components-panel-bg p-4">
            <div className="text-xs text-text-quaternary">下级累计消耗</div>
            <div className="mt-1 text-xl font-bold text-text-primary">
              ¥
              {Number(summary.total_consumption).toFixed(2)}
            </div>
          </div>
          <div className="rounded-xl border border-divider-regular bg-components-panel-bg p-4">
            <div className="text-xs text-text-quaternary">邀请人数</div>
            <div className="mt-1 text-xl font-bold text-text-primary">
              {summary.invitee_count}
            </div>
          </div>
        </div>
      )}

      {/* Records table */}
      <div>
        <div className="mb-3 text-sm font-semibold text-text-primary">返点明细</div>
        {loading
          ? (
              <div className="flex items-center justify-center py-12">
                <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
              </div>
            )
          : records.length === 0
            ? (
                <div className="rounded-xl border border-dashed border-divider-regular p-8 text-center">
                  <div className="text-text-tertiary">暂无返点记录</div>
                  <div className="mt-1 text-xs text-text-quaternary">邀请下级用户后，其消耗将在次日产生返点收入</div>
                </div>
              )
            : (
                <>
                  <div className="rounded-xl border border-divider-regular overflow-hidden">
                    {/* Header */}
                    <div className="flex h-9 items-center border-b border-divider-regular bg-background-section text-xs font-semibold text-text-tertiary">
                      <div className="w-28 shrink-0 px-3">结算日期</div>
                      <div className="w-32 shrink-0 px-3">下级用户</div>
                      <div className="w-28 shrink-0 px-3 text-right">消耗金额</div>
                      <div className="w-28 shrink-0 px-3 text-right">成本扣除</div>
                      <div className="w-28 shrink-0 px-3 text-right">返点金额</div>
                      <div className="w-20 shrink-0 px-3 text-right">返点比例</div>
                    </div>
                    {/* Rows */}
                    {records.map(r => (
                      <div key={r.id} className="flex h-10 items-center border-b border-divider-subtle text-sm text-text-secondary last:border-b-0">
                        <div className="w-28 shrink-0 px-3 text-text-tertiary">{r.settlement_date}</div>
                        <div className="w-32 shrink-0 truncate px-3">{r.invitee_name || `${r.invitee_account_id.slice(0, 8)}...`}</div>
                        <div className="w-28 shrink-0 px-3 text-right font-mono">
                          ¥
                          {Number(r.consumption_amount).toFixed(2)}
                        </div>
                        <div className="w-28 shrink-0 px-3 text-right font-mono text-text-quaternary">
                          {Number(r.cost_amount) > 0 ? `¥${Number(r.cost_amount).toFixed(2)}` : '-'}
                        </div>
                        <div className="w-28 shrink-0 px-3 text-right font-mono font-medium text-state-success-text">
                          +¥
                          {Number(r.rebate_amount).toFixed(2)}
                        </div>
                        <div className="w-20 shrink-0 px-3 text-right text-text-quaternary">
                          {Number(r.rebate_rate)}
                          %
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="mt-3 flex items-center justify-between text-xs text-text-tertiary">
                      <div>
                        共
                        {total}
                        {' '}
                        条记录
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          disabled={page <= 1}
                          onClick={() => setPage(p => Math.max(1, p - 1))}
                          className="rounded px-2 py-1 hover:bg-state-base-hover disabled:opacity-40"
                        >
                          上一页
                        </button>
                        <span>
                          {page}
                          {' '}
                          /
                          {' '}
                          {totalPages}
                        </span>
                        <button
                          type="button"
                          disabled={page >= totalPages}
                          onClick={() => setPage(p => p + 1)}
                          className="rounded px-2 py-1 hover:bg-state-base-hover disabled:opacity-40"
                        >
                          下一页
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
      </div>
    </div>
  )
}
