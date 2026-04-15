import type { TopupOrderStatus } from '@/service/wallet'

export type OrderStatusFilter = TopupOrderStatus | 'all'

export const STATUS_LABELS: Record<TopupOrderStatus, string> = {
  pending: '待支付',
  paid: '已支付',
  closed: '已关闭',
  expired: '已过期',
  failed: '已失败',
}

export const STATUS_COLORS: Record<TopupOrderStatus, string> = {
  pending: 'bg-state-warning-hover text-state-warning-text',
  paid: 'bg-state-success-hover text-state-success-text',
  closed: 'bg-background-section text-text-tertiary',
  expired: 'bg-background-section text-text-tertiary',
  failed: 'bg-state-destructive-hover text-state-destructive-text',
}
