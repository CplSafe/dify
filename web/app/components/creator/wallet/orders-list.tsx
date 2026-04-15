'use client'

/**
 * Topup orders list — shared between owner-side history and super-admin.
 *
 * Renders one row per ``PaymentOrder`` with status pill, amount, timestamps,
 * and (for the owner view) actions on pending orders: 继续支付 / 取消订单.
 *
 * Super-admin mode omits per-row actions — operations staff read-only browses
 * the list to investigate stuck payments. Action gating is a prop rather than
 * a role lookup so the table stays dumb about auth.
 */

import type { TopupOrder, TopupOrderStatus } from '@/service/wallet'
import { RiExternalLinkLine, RiLoader4Line } from '@remixicon/react'
import { useCallback } from 'react'
import Button from '@/app/components/base/button'
import { cn } from '@/utils/classnames'
import { STATUS_COLORS, STATUS_LABELS } from './orders-constants'

const formatDateTime = (iso: string | null) => {
  if (!iso)
    return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatYuan = (value: string | number) => {
  const n = typeof value === 'string' ? Number(value) : value
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
}

type Props = {
  orders: TopupOrder[]
  loading: boolean
  /** Show the tenant/account columns (super-admin view). */
  showOwnerColumns?: boolean
  /** Enable per-row actions (owner view only). */
  allowActions?: boolean
  onContinuePay?: (order: TopupOrder) => void
  onCancel?: (order: TopupOrder) => void | Promise<void>
  /** Per-row busy flag, keyed by out_trade_no, so actions can disable. */
  busyOrderNos?: Set<string>
}

export default function OrdersList({
  orders,
  loading,
  showOwnerColumns = false,
  allowActions = false,
  onContinuePay,
  onCancel,
  busyOrderNos,
}: Props) {
  const isBusy = useCallback(
    (out_trade_no: string) => busyOrderNos?.has(out_trade_no) ?? false,
    [busyOrderNos],
  )

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
      </div>
    )
  }

  if (orders.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-divider-subtle py-12 text-sm text-text-quaternary">
        暂无订单
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-divider-subtle">
      <div className="flex items-center border-b border-divider-regular py-[7px] system-xs-medium-uppercase text-text-tertiary">
        <div className="w-[200px] shrink-0 px-4">订单号</div>
        {showOwnerColumns && (
          <>
            <div className="w-[140px] shrink-0 px-4">工作区</div>
            <div className="w-[140px] shrink-0 px-4">账号</div>
          </>
        )}
        <div className="w-[100px] shrink-0 px-4">状态</div>
        <div className="w-[100px] shrink-0 px-4 text-right">金额</div>
        <div className="w-[160px] shrink-0 px-4">创建时间</div>
        <div className="w-[160px] shrink-0 px-4">支付时间</div>
        {allowActions && <div className="grow px-4 text-right">操作</div>}
      </div>
      {orders.map((o) => {
        const status = o.status as TopupOrderStatus
        const busy = isBusy(o.out_trade_no)
        return (
          <div
            key={o.order_id}
            className="flex items-center border-b border-divider-subtle last:border-0"
          >
            <div className="w-[200px] shrink-0 truncate px-4 py-3 system-xs-regular text-text-secondary">
              {o.out_trade_no}
            </div>
            {showOwnerColumns && (
              <>
                <div className="w-[140px] shrink-0 truncate px-4 py-3 system-xs-regular text-text-tertiary">
                  {o.tenant_id.slice(0, 8)}
                  …
                </div>
                <div className="w-[140px] shrink-0 truncate px-4 py-3 system-xs-regular text-text-tertiary">
                  {o.account_id.slice(0, 8)}
                  …
                </div>
              </>
            )}
            <div className="w-[100px] shrink-0 px-4 py-3">
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-xs font-medium',
                  STATUS_COLORS[status],
                )}
              >
                {STATUS_LABELS[status]}
              </span>
            </div>
            <div className="w-[100px] shrink-0 px-4 py-3 text-right system-sm-semibold text-text-secondary tabular-nums">
              ¥
              {formatYuan(o.amount_yuan)}
            </div>
            <div className="w-[160px] shrink-0 px-4 py-3 system-xs-regular text-text-tertiary">
              {formatDateTime(o.created_at)}
            </div>
            <div className="w-[160px] shrink-0 px-4 py-3 system-xs-regular text-text-tertiary">
              {formatDateTime(o.paid_at)}
            </div>
            {allowActions && (
              <div className="flex grow items-center justify-end gap-2 px-4 py-2">
                {status === 'pending' && onContinuePay && (
                  <Button
                    size="small"
                    variant="primary"
                    disabled={busy}
                    onClick={() => onContinuePay(o)}
                  >
                    <RiExternalLinkLine className="mr-1 h-3.5 w-3.5" />
                    继续支付
                  </Button>
                )}
                {status === 'pending' && onCancel && (
                  <Button
                    size="small"
                    disabled={busy}
                    onClick={() => void onCancel(o)}
                  >
                    取消
                  </Button>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
