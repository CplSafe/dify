'use client'
/* eslint-disable react/set-state-in-effect -- TODO(wallet): reset-on-close uses effect-driven state reset; refactor to event-driven later */

/**
 * Topup modal — owner-only Alipay self-service topup.
 *
 * Two-step flow:
 *   1. Pick amount + payment method, POST /workspaces/current/topup/orders.
 *   2. Render the upstream qr_code (QR provider) or open pay_url in a new
 *      window (Page provider), then poll the order until paid / closed /
 *      expired.
 *
 * Closing the modal mid-flight calls /close so the order doesn't sit pending
 * forever (Celery would clean it up eventually, but eager close is friendlier
 * to the operator's order list).
 */

import type { CreateTopupOrderResponse, TopupOrder } from '@/service/wallet'
import {
  RiArrowLeftLine,
  RiCheckboxCircleFill,
  RiCloseLine,
  RiLoader4Line,
} from '@remixicon/react'
import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { Dialog, DialogContent } from '@/app/components/base/ui/dialog'
import { toast } from '@/app/components/base/ui/toast'
import {
  closeTopupOrder,
  createTopupOrder,
  fetchTopupOrder,
} from '@/service/wallet'
import { cn } from '@/utils/classnames'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called after a successful topup so the wallet pill can refresh. */
  onPaid?: () => void
}

type PaymentMethod = 'alipay' | 'wechat'

const PRESET_AMOUNTS_YUAN = [10, 50, 100, 500] as const
// Informational only — the backend is the source of truth for per-order
// min/max (ALIPAY_MIN_AMOUNT_FEN / ALIPAY_MAX_AMOUNT_FEN). We don't gate
// on either bound client-side: any positive number is allowed through, and
// the backend's error message is surfaced via toast if it's out of range.
// This keeps PC-channel small-amount payments working without a frontend
// redeploy when the operator tweaks the min.
const SINGLE_ORDER_LIMIT_YUAN = 100_000
const POLL_INTERVAL_MS = 2000
const POLL_FAILURE_BACKOFF_MS = 5000
const POLL_MAX_FAILURES = 3
const TERMINAL_STATUSES = new Set(['paid', 'closed', 'expired', 'failed'])

function formatYuan(value: string | number): string {
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n))
    return '0.00'
  return n.toFixed(2)
}

function useCountdown(expiresAtIso: string | null): string {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!expiresAtIso)
      return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [expiresAtIso])

  if (!expiresAtIso)
    return ''
  const expiresAt = new Date(expiresAtIso).getTime()
  const remaining = Math.max(0, Math.floor((expiresAt - now) / 1000))
  const minutes = Math.floor(remaining / 60)
  const seconds = remaining % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export default function TopupModal({ open, onOpenChange, onPaid }: Props) {
  const [step, setStep] = useState<'amount' | 'pay' | 'success'>('amount')
  const [amountYuan, setAmountYuan] = useState<string>('')
  const [method, setMethod] = useState<PaymentMethod>('alipay')
  const [submitting, setSubmitting] = useState(false)
  const [order, setOrder] = useState<CreateTopupOrderResponse | null>(null)
  const [polledOrder, setPolledOrder] = useState<TopupOrder | null>(null)
  const [pollError, setPollError] = useState<string | null>(null)

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pollFailureCountRef = useRef(0)
  const pollStoppedRef = useRef(false)

  const stopPolling = useCallback(() => {
    pollStoppedRef.current = true
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const resetState = useCallback(() => {
    stopPolling()
    setStep('amount')
    setAmountYuan('')
    setMethod('alipay')
    setSubmitting(false)
    setOrder(null)
    setPolledOrder(null)
    setPollError(null)
    pollFailureCountRef.current = 0
    pollStoppedRef.current = false
  }, [stopPolling])

  // Reset when modal closes.
  useEffect(() => {
    if (!open)
      resetState()
  }, [open, resetState])

  // Cleanup polling on unmount.
  useEffect(() => () => stopPolling(), [stopPolling])

  const presetSelected = useMemo(() => {
    const n = Number(amountYuan)
    return PRESET_AMOUNTS_YUAN.find(p => p === n) ?? null
  }, [amountYuan])

  // Only block empty / non-numeric / non-positive input — the backend is
  // the source of truth for min/max so users aren't double-gated by a
  // stale UI copy. PC-channel支付 has no hard floor, so we accept anything
  // > 0 and let the backend reject it if it's below ALIPAY_MIN_AMOUNT_FEN.
  const amountInvalid = useMemo(() => {
    const n = Number(amountYuan)
    if (!amountYuan || !Number.isFinite(n))
      return true
    return n <= 0
  }, [amountYuan])

  const startPolling = useCallback(
    (outTradeNo: string) => {
      pollStoppedRef.current = false
      pollFailureCountRef.current = 0

      const tick = async () => {
        if (pollStoppedRef.current)
          return
        try {
          const fresh = await fetchTopupOrder(outTradeNo)
          pollFailureCountRef.current = 0
          setPolledOrder(fresh)
          setPollError(null)
          if (TERMINAL_STATUSES.has(fresh.status)) {
            stopPolling()
            if (fresh.status === 'paid') {
              setStep('success')
              onPaid?.()
              // Auto-dismiss after a beat so users see the success state.
              // 3s gives users returning from the Alipay tab enough time to
              // register the green ✅ before the modal disappears; they can
              // also click 完成 to close immediately.
              setTimeout(() => onOpenChange(false), 3000)
            }
            else {
              setPollError(
                fresh.status === 'expired'
                  ? '订单已超时，请重新发起'
                  : fresh.status === 'closed'
                    ? '订单已关闭'
                    : '支付失败，请重试',
              )
            }
            return
          }
        }
        catch {
          pollFailureCountRef.current += 1
          if (pollFailureCountRef.current >= POLL_MAX_FAILURES) {
            stopPolling()
            setPollError('查询订单状态失败，请关闭弹窗后重试')
            return
          }
        }

        const delay
          = pollFailureCountRef.current > 0
            ? POLL_FAILURE_BACKOFF_MS
            : POLL_INTERVAL_MS
        pollTimerRef.current = setTimeout(tick, delay)
      }

      pollTimerRef.current = setTimeout(tick, POLL_INTERVAL_MS)
    },
    [onOpenChange, onPaid, stopPolling],
  )

  const handleSubmit = useCallback(async () => {
    if (amountInvalid)
      return
    if (method !== 'alipay') {
      toast.error('该支付方式暂未上线')
      return
    }
    setSubmitting(true)
    try {
      const created = await createTopupOrder({
        amount_yuan: Number(amountYuan),
        subject: '钱包充值',
      })
      setOrder(created)
      setPolledOrder(null)
      setPollError(null)
      setStep('pay')
      // If the upstream returned a redirect URL (PC web channel), open it now.
      if (created.pay_url && !created.qr_code)
        window.open(created.pay_url, '_blank', 'noopener,noreferrer')
      startPolling(created.out_trade_no)
    }
    catch (err: unknown) {
      const message
        = err instanceof Error ? err.message : '创建订单失败，请稍后重试'
      toast.error(message)
    }
    finally {
      setSubmitting(false)
    }
  }, [amountInvalid, amountYuan, method, startPolling])

  const handleClose = useCallback(async () => {
    // Try to release the pending order on the backend so it doesn't linger.
    if (
      order
      && polledOrder?.status !== 'paid'
      && polledOrder?.status !== 'closed'
    ) {
      try {
        await closeTopupOrder(order.out_trade_no)
      }
      catch {
        // Best-effort; Celery will eventually expire the order anyway.
      }
    }
    onOpenChange(false)
  }, [onOpenChange, order, polledOrder])

  const handleBack = useCallback(async () => {
    if (
      order
      && polledOrder?.status !== 'paid'
      && polledOrder?.status !== 'closed'
    ) {
      try {
        await closeTopupOrder(order.out_trade_no)
      }
      catch {
        // Same rationale as in handleClose.
      }
    }
    stopPolling()
    setOrder(null)
    setPolledOrder(null)
    setPollError(null)
    setStep('amount')
  }, [order, polledOrder, stopPolling])

  const countdown = useCountdown(order?.expires_at ?? null)

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next)
          void handleClose()
        else onOpenChange(true)
      }}
    >
      <DialogContent className="w-[480px] max-w-[95vw] p-0">
        <div className="flex items-center justify-between border-b border-divider-subtle px-6 py-4">
          <div className="flex items-center gap-2">
            {step === 'pay' && (
              <button
                type="button"
                onClick={() => void handleBack()}
                className="rounded-md p-1 text-text-tertiary hover:bg-state-base-hover"
                aria-label="返回"
              >
                <RiArrowLeftLine className="h-4 w-4" />
              </button>
            )}
            <h2 className="text-base font-semibold text-text-primary">
              {step === 'success' ? '充值成功' : '钱包充值'}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => void handleClose()}
            className="rounded-md p-1 text-text-tertiary hover:bg-state-base-hover"
            aria-label="关闭"
          >
            <RiCloseLine className="h-4 w-4" />
          </button>
        </div>

        {step === 'amount' && (
          <div className="space-y-5 px-6 py-5">
            <div>
              <div className="mb-2 text-xs font-medium text-text-tertiary">
                选择金额
              </div>
              <div className="grid grid-cols-4 gap-2">
                {PRESET_AMOUNTS_YUAN.map(amount => (
                  <button
                    key={amount}
                    type="button"
                    onClick={() => setAmountYuan(String(amount))}
                    className={cn(
                      'rounded-lg border px-3 py-2.5 text-sm font-semibold transition-colors',
                      presetSelected === amount
                        ? 'border-primary-500 bg-primary-50 text-primary-700'
                        : 'border-divider-subtle bg-components-input-bg-normal text-text-secondary hover:border-divider-regular',
                    )}
                  >
                    ¥
                    {amount}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-2 text-xs font-medium text-text-tertiary">
                自定义金额（元）
              </div>
              <Input
                type="number"
                inputMode="decimal"
                value={amountYuan}
                onChange={e => setAmountYuan(e.target.value)}
                placeholder="请输入充值金额"
                min={0}
                step="0.01"
              />
              {amountYuan && amountInvalid && (
                <div className="text-state-destructive-text mt-1 text-xs">
                  请输入有效的金额
                </div>
              )}
              <div className="mt-1 text-xs text-text-tertiary">
                单笔充值上限 ¥
                {SINGLE_ORDER_LIMIT_YUAN.toLocaleString()}
              </div>
            </div>

            <div>
              <div className="mb-2 text-xs font-medium text-text-tertiary">
                支付方式
              </div>
              <div className="space-y-2">
                <label
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors',
                    method === 'alipay'
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-divider-subtle hover:border-divider-regular',
                  )}
                >
                  <input
                    type="radio"
                    name="payment-method"
                    value="alipay"
                    checked={method === 'alipay'}
                    onChange={() => setMethod('alipay')}
                    className="h-4 w-4 accent-primary-600"
                  />
                  <span className="text-sm font-medium text-text-secondary">
                    支付宝
                  </span>
                </label>
                <label
                  className={cn(
                    'flex cursor-not-allowed items-center gap-3 rounded-lg border border-divider-subtle px-3 py-2.5 opacity-60',
                  )}
                  title="即将上线"
                >
                  <input
                    type="radio"
                    name="payment-method"
                    value="wechat"
                    disabled
                    className="h-4 w-4"
                  />
                  <span className="text-sm font-medium text-text-secondary">
                    微信支付
                  </span>
                  <span className="ml-auto text-xs text-text-quaternary">
                    即将上线
                  </span>
                </label>
              </div>
            </div>

            <div className="flex justify-end pt-1">
              <Button
                variant="primary"
                disabled={amountInvalid || submitting}
                onClick={() => void handleSubmit()}
              >
                {submitting ? '正在创建订单…' : '立即支付'}
              </Button>
            </div>
          </div>
        )}

        {step === 'pay' && order && (
          <div className="space-y-4 px-6 py-5">
            <div className="text-center">
              <div className="text-xs text-text-tertiary">待支付金额</div>
              <div className="mt-1 text-3xl font-bold text-text-primary">
                ¥
                {formatYuan(order.amount_yuan)}
              </div>
            </div>

            {order.qr_code && (
              <div className="flex flex-col items-center gap-3 rounded-xl border border-divider-subtle bg-white p-6">
                <QRCodeSVG value={order.qr_code} size={200} level="M" />
                <div className="text-sm text-text-secondary">
                  请使用支付宝扫码支付
                </div>
                {countdown && (
                  <div className="text-xs text-text-tertiary">
                    剩余支付时间
                    {' '}
                    {countdown}
                  </div>
                )}
              </div>
            )}

            {!order.qr_code && order.pay_url && (
              <div className="rounded-xl border border-divider-subtle bg-components-input-bg-normal p-5 text-center">
                <RiLoader4Line className="text-primary-600 mx-auto mb-3 h-6 w-6 animate-spin" />
                <div className="text-sm text-text-secondary">
                  已为您打开支付宝收银台
                </div>
                <div className="mt-1 text-xs text-text-tertiary">
                  支付完成后此页面会自动刷新
                </div>
                <button
                  type="button"
                  className="text-primary-600 mt-3 text-xs hover:underline"
                  onClick={() =>
                    window.open(order.pay_url!, '_blank', 'noopener,noreferrer')}
                >
                  没看到支付页？点此重新打开
                </button>
              </div>
            )}

            <div className="flex items-center justify-center gap-2 text-xs text-text-tertiary">
              <RiLoader4Line className="h-3.5 w-3.5 animate-spin" />
              <span>等待支付结果…</span>
            </div>

            {pollError && (
              <div className="text-state-destructive-text rounded-lg bg-state-destructive-hover px-3 py-2 text-xs">
                {pollError}
              </div>
            )}
          </div>
        )}

        {step === 'success' && (
          <div className="flex flex-col items-center justify-center gap-4 px-6 py-10">
            <RiCheckboxCircleFill className="text-state-success-text h-14 w-14" />
            <div className="text-lg font-semibold text-text-primary">
              充值成功
            </div>
            {polledOrder && (
              <div className="text-sm text-text-tertiary">
                ¥
                {formatYuan(polledOrder.amount)}
                {' '}
                已到账
              </div>
            )}
            <Button
              variant="primary"
              onClick={() => onOpenChange(false)}
              className="mt-2"
            >
              完成
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
