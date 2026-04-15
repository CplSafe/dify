'use client'

/**
 * Owner-side top-up orders page.
 *
 * Lists the current workspace's PaymentOrders with a status filter, paginated.
 * Pending orders expose two actions:
 *
 *   - 继续支付 — re-open the saved ``pay_url`` in a new tab. No new order is
 *     created; the original is still valid until ``expires_at``.
 *   - 取消 — calls the close endpoint, flipping status to ``closed``.
 *
 * Non-owners hit a 403 from the backend; we rely on that rather than gating
 * in the UI so the source of truth stays server-side.
 */

import type { OrderStatusFilter } from './orders-constants'
import type { TopupOrder } from '@/service/wallet'
import { useCallback, useEffect, useMemo, useState } from 'react'
import Button from '@/app/components/base/button'
import { toast } from '@/app/components/base/ui/toast'
import { closeTopupOrder, listTopupOrders } from '@/service/wallet'
import { cn } from '@/utils/classnames'
import { STATUS_LABELS } from './orders-constants'
import OrdersList from './orders-list'

const PAGE_SIZE = 20

const FILTER_TABS: { key: OrderStatusFilter, label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: STATUS_LABELS.pending },
  { key: 'paid', label: STATUS_LABELS.paid },
  { key: 'closed', label: STATUS_LABELS.closed },
  { key: 'expired', label: STATUS_LABELS.expired },
]

export default function WalletOrdersPage() {
  const [filter, setFilter] = useState<OrderStatusFilter>('all')
  const [orders, setOrders] = useState<TopupOrder[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<Set<string>>(() => new Set())

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listTopupOrders({
        limit: PAGE_SIZE,
        offset,
        status: filter === 'all' ? undefined : filter,
      })
      setOrders(res.data)
      setTotal(res.total)
    }
    catch {
      toast.error('加载订单失败')
    }
    finally {
      setLoading(false)
    }
  }, [filter, offset])

  useEffect(() => {
    void load()
  }, [load])

  // Wrapping setFilter so changing the filter also resets pagination in a
  // single render — avoids the set-state-in-effect anti-pattern.
  const changeFilter = useCallback((next: OrderStatusFilter) => {
    setFilter(next)
    setOffset(0)
  }, [])

  const withBusy = useCallback(
    async (outTradeNo: string, fn: () => Promise<unknown>) => {
      setBusy(prev => new Set(prev).add(outTradeNo))
      try {
        await fn()
      }
      finally {
        setBusy((prev) => {
          const next = new Set(prev)
          next.delete(outTradeNo)
          return next
        })
      }
    },
    [],
  )

  const handleContinuePay = useCallback((order: TopupOrder) => {
    if (order.pay_url) {
      window.open(order.pay_url, '_blank', 'noopener,noreferrer')
      return
    }
    // QR-channel orders have no resumable URL — the user needs to cancel
    // and re-open the wallet modal to scan a fresh code.
    toast.error('该订单为扫码支付，请取消后重新发起充值')
  }, [])

  const handleCancel = useCallback(
    async (order: TopupOrder) => {
      await withBusy(order.out_trade_no, async () => {
        try {
          await closeTopupOrder(order.out_trade_no)
          toast.success('订单已取消')
          await load()
        }
        catch {
          toast.error('取消订单失败')
        }
      })
    },
    [load, withBusy],
  )

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  )
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
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

      <OrdersList
        orders={orders}
        loading={loading}
        allowActions
        onContinuePay={handleContinuePay}
        onCancel={handleCancel}
        busyOrderNos={busy}
      />

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
