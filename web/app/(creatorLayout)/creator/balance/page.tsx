import BalanceTab from '@/app/components/creator/settings/tabs/balance-tab'

export default function CreatorBalancePage() {
  return (
    <div className="flex h-full min-h-0 flex-col bg-background-default">
      <div className="shrink-0 border-b border-divider-subtle px-8 pb-6 pt-8">
        <h1 className="text-2xl font-bold text-text-primary">充值页</h1>
        <p className="mt-2 text-sm text-text-tertiary">查看当前余额和账单记录；如余额不足，请联系管理员完成充值。</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <BalanceTab />
      </div>
    </div>
  )
}
