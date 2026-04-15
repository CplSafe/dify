import AdminTopupOrdersPage from '@/app/components/creator/wallet/admin-orders-page'

export default function Page() {
  return (
    <div className="flex h-full min-h-0 flex-col bg-background-default">
      <div className="shrink-0 border-b border-divider-subtle px-8 pt-8 pb-6">
        <h1 className="text-2xl font-bold text-text-primary">
          支付订单（超管）
        </h1>
        <p className="mt-2 text-sm text-text-tertiary">
          查看全平台所有充值订单，包含待支付 / 已关闭 / 已过期。
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <AdminTopupOrdersPage />
      </div>
    </div>
  )
}
