'use client'

/**
 * Allocation modal — workspace owner allocates funds to or reclaims funds
 * from a workspace member.
 *
 * Amount contract matches the backend: signed decimal yuan. Positive
 * allocates tenant → member, negative reclaims member → tenant. Zero is
 * rejected here and by the service.
 *
 * The UI keeps a sign toggle separate from the magnitude input so members
 * never see a minus sign sneak in by accident; we assemble the signed
 * amount right before calling allocateToMember.
 */

import type { AllocationRecord } from '@/service/wallet'
import { RiArrowLeftRightLine, RiCloseLine } from '@remixicon/react'
import { useCallback, useMemo, useState } from 'react'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { Dialog, DialogContent } from '@/app/components/base/ui/dialog'
import { toast } from '@/app/components/base/ui/toast'
import { allocateToMember } from '@/service/wallet'
import { cn } from '@/utils/classnames'

type Direction = 'allocate' | 'reclaim'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  memberId: string
  memberName: string
  memberBalance: string
  /** Workspace wallet balance (what the owner can allocate out of). */
  tenantBalance?: string
  onSuccess?: (record: AllocationRecord) => void
}

const MAX_YUAN = 1_000_000

const formatYuan = (value: string): string => {
  const n = Number(value)
  if (!Number.isFinite(n))
    return '0.00'
  return n.toFixed(2)
}

export default function AllocationModal({
  open,
  onOpenChange,
  memberId,
  memberName,
  memberBalance,
  tenantBalance,
  onSuccess,
}: Props) {
  // The parent conditionally renders this modal per-target, so initial
  // state is always fresh on mount — no reset effect needed.
  const [direction, setDirection] = useState<Direction>('allocate')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const amountNumber = useMemo(() => {
    const n = Number(amount)
    return Number.isFinite(n) ? n : 0
  }, [amount])

  const errorMessage = useMemo(() => {
    if (!amount)
      return null
    if (amountNumber <= 0)
      return '金额必须大于 0'
    if (amountNumber > MAX_YUAN)
      return `金额不能超过 ¥${MAX_YUAN.toLocaleString()}`
    if (direction === 'reclaim' && amountNumber > Number(memberBalance))
      return '回收金额不能超过成员余额'
    if (
      direction === 'allocate'
      && tenantBalance !== undefined
      && amountNumber > Number(tenantBalance)
    ) {
      return '分配金额不能超过空间余额'
    }
    return null
  }, [amount, amountNumber, direction, memberBalance, tenantBalance])

  const canSubmit = amount !== '' && !errorMessage && !submitting

  const handleSubmit = useCallback(async () => {
    if (!canSubmit)
      return
    setSubmitting(true)
    try {
      const signed = direction === 'allocate' ? amountNumber : -amountNumber
      const record = await allocateToMember(memberId, {
        amount_yuan: signed,
        description: description.trim() || undefined,
      })
      toast.success(direction === 'allocate' ? '分配成功' : '回收成功')
      onSuccess?.(record)
      onOpenChange(false)
    }
    catch (err: unknown) {
      const message
        = err instanceof Error ? err.message : '操作失败，请稍后重试'
      toast.error(message)
    }
    finally {
      setSubmitting(false)
    }
  }, [
    amountNumber,
    canSubmit,
    description,
    direction,
    memberId,
    onOpenChange,
    onSuccess,
  ])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[440px] max-w-[95vw] p-0">
        <div className="flex items-center justify-between border-b border-divider-subtle px-6 py-4">
          <h2 className="text-base font-semibold text-text-primary">
            额度分配
          </h2>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-md p-1 text-text-tertiary hover:bg-state-base-hover"
            aria-label="关闭"
          >
            <RiCloseLine className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className="rounded-lg bg-background-section px-3 py-2.5">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="truncate text-xs text-text-tertiary">成员</div>
                <div className="mt-0.5 truncate text-sm font-medium text-text-primary">
                  {memberName}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs text-text-tertiary">当前余额</div>
                <div className="mt-0.5 text-sm font-semibold text-text-primary tabular-nums">
                  ¥
                  {formatYuan(memberBalance)}
                </div>
              </div>
            </div>
            {tenantBalance !== undefined && (
              <div className="mt-2 flex items-center justify-between border-t border-divider-subtle pt-2 text-xs text-text-tertiary">
                <span>空间可分配余额</span>
                <span className="tabular-nums">
                  ¥
                  {formatYuan(tenantBalance)}
                </span>
              </div>
            )}
          </div>

          <div>
            <div className="mb-2 text-xs font-medium text-text-tertiary">
              操作类型
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setDirection('allocate')}
                className={cn(
                  'rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors',
                  direction === 'allocate'
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-divider-subtle bg-components-input-bg-normal text-text-secondary hover:border-divider-regular',
                )}
              >
                分配额度
              </button>
              <button
                type="button"
                onClick={() => setDirection('reclaim')}
                className={cn(
                  'rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors',
                  direction === 'reclaim'
                    ? 'text-state-warning-text border-state-warning-solid bg-state-warning-hover/60'
                    : 'border-divider-subtle bg-components-input-bg-normal text-text-secondary hover:border-divider-regular',
                )}
              >
                回收额度
              </button>
            </div>
          </div>

          <div>
            <div className="mb-2 text-xs font-medium text-text-tertiary">
              金额（元）
            </div>
            <Input
              type="number"
              inputMode="decimal"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              placeholder="请输入金额"
              min={0}
              max={MAX_YUAN}
              step="0.01"
            />
            {errorMessage && (
              <div className="text-state-destructive-text mt-1 text-xs">
                {errorMessage}
              </div>
            )}
          </div>

          <div>
            <div className="mb-2 text-xs font-medium text-text-tertiary">
              备注（可选）
            </div>
            <Input
              type="text"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="用于审计记录，最多 256 字"
              maxLength={256}
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-1.5 text-xs text-text-tertiary">
              <RiArrowLeftRightLine className="h-3.5 w-3.5" />
              <span>
                {direction === 'allocate' ? '空间 → 成员' : '成员 → 空间'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={() => onOpenChange(false)}>取消</Button>
              <Button
                variant="primary"
                disabled={!canSubmit}
                onClick={() => void handleSubmit()}
              >
                {submitting ? '提交中…' : '确认'}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
