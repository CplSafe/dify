import WalletOrdersPage from '@/app/components/creator/wallet/orders-page'

export default function Page() {
  return (
    <div className="flex h-full min-h-0 flex-col bg-background-default">
      <div className="shrink-0 border-b border-divider-subtle px-8 pt-8 pb-6">
        <h1 className="text-2xl font-bold text-text-primary">充值订单</h1>
        <p className="mt-2 text-sm text-text-tertiary">
          查看工作区的充值订单记录，待支付订单可继续支付或取消。
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <WalletOrdersPage />
      </div>
    </div>
  )
}
