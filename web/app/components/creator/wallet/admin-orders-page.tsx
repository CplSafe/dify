'use client'

/**
 * Super-admin top-up orders page.
 *
 * Platform-wide list of PaymentOrders with status / tenant_id / account_id
 * filters. Read-only — the admin doesn't close or resume orders here, they
 * audit. If ops ever needs to force-close from the UI, wire the existing
 * close endpoint through (it's already owner-scoped, so we'd need an
 * admin variant backend-side too).
 */

import type { OrderStatusFilter } from './orders-constants'
import type { TopupOrder } from '@/service/wallet'
import { useCallback, useEffect, useMemo, useState } from 'react'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { toast } from '@/app/components/base/ui/toast'
import { useAppContext } from '@/context/app-context'
import { listAdminTopupOrders } from '@/service/wallet'
import { cn } from '@/utils/classnames'
import { STATUS_LABELS } from './orders-constants'
import OrdersList from './orders-list'

const PAGE_SIZE = 50

const FILTER_TABS: { key: OrderStatusFilter, label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: STATUS_LABELS.pending },
  { key: 'paid', label: STATUS_LABELS.paid },
  { key: 'closed', label: STATUS_LABELS.closed },
  { key: 'expired', label: STATUS_LABELS.expired },
  { key: 'failed', label: STATUS_LABELS.failed },
]

export default function AdminTopupOrdersPage() {
  const { isSystemAdmin } = useAppContext()

  const [filter, setFilter] = useState<OrderStatusFilter>('all')
  const [tenantId, setTenantId] = useState('')
  const [accountId, setAccountId] = useState('')
  const [appliedTenantId, setAppliedTenantId] = useState('')
  const [appliedAccountId, setAppliedAccountId] = useState('')

  const [orders, setOrders] = useState<TopupOrder[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!isSystemAdmin)
      return
    setLoading(true)
    try {
      const res = await listAdminTopupOrders({
        limit: PAGE_SIZE,
        offset,
        status: filter === 'all' ? undefined : filter,
        tenant_id: appliedTenantId || undefined,
        account_id: appliedAccountId || undefined,
      })
      setOrders(res.data)
      setTotal(res.total)
    }
    catch {
      toast.error('加载订单失败（需超管权限）')
    }
    finally {
      setLoading(false)
    }
  }, [isSystemAdmin, offset, filter, appliedTenantId, appliedAccountId])

  useEffect(() => {
    void load()
  }, [load])

  // Each filter mutator also resets offset in the same render, avoiding the
  // set-state-in-effect anti-pattern and the extra render it implies.
  const changeFilter = useCallback((next: OrderStatusFilter) => {
    setFilter(next)
    setOffset(0)
  }, [])

  const applyFilters = useCallback(() => {
    setAppliedTenantId(tenantId.trim())
    setAppliedAccountId(accountId.trim())
    setOffset(0)
  }, [tenantId, accountId])

  const resetFilters = useCallback(() => {
    setTenantId('')
    setAccountId('')
    setAppliedTenantId('')
    setAppliedAccountId('')
    setOffset(0)
  }, [])

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  )
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  if (!isSystemAdmin) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-divider-subtle py-12 text-sm text-text-quaternary">
        仅超级管理员可访问此页面
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {FILTER_TABS.map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => changeFilter(t.key)}
            className={cn(
              'rounded-lg px-3 py-1.5 text-sm transition-colors',
              filter === t.key
                ? 'bg-components-button-secondary-bg text-text-primary'
                : 'text-text-tertiary hover:bg-state-base-hover hover:text-text-secondary',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-divider-subtle p-4">
        <div className="min-w-[200px] flex-1">
          <div className="mb-1 text-xs font-medium text-text-tertiary">
            工作区 ID
          </div>
          <Input
            value={tenantId}
            onChange={e => setTenantId(e.target.value)}
            placeholder="tenant_id"
          />
        </div>
        <div className="min-w-[200px] flex-1">
          <div className="mb-1 text-xs font-medium text-text-tertiary">
            账号 ID
          </div>
          <Input
            value={accountId}
            onChange={e => setAccountId(e.target.value)}
            placeholder="account_id"
          />
        </div>
        <Button variant="primary" onClick={applyFilters}>
          查询
        </Button>
        <Button onClick={resetFilters}>重置</Button>
      </div>

      <OrdersList orders={orders} loading={loading} showOwnerColumns />

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-3 text-sm text-text-tertiary">
          <span>
            第
            {' '}
            {currentPage}
            {' '}
            /
            {' '}
            {totalPages}
            {' '}
            页，共
            {' '}
            {total}
            {' '}
            条
          </span>
          <Button
            size="small"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            上一页
          </Button>
          <Button
            size="small"
            disabled={offset + PAGE_SIZE >= total || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}
