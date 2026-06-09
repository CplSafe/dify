'use client'

import type { WalletSummary } from '@/contract/console/agent'
import * as React from 'react'
import { useTranslation } from 'react-i18next'

type WalletCardProps = {
  wallet: WalletSummary
}

const Metric = ({ label, value, accent }: { label: string, value: string, accent?: boolean }) => (
  <div className="flex flex-col gap-1">
    <span className="text-xs text-text-tertiary">{label}</span>
    <span
      className={`text-2xl font-semibold ${accent ? 'text-text-accent' : 'text-text-primary'}`}
    >
      ¥
      {value}
    </span>
  </div>
)

const WalletCard = ({ wallet }: WalletCardProps) => {
  const { t } = useTranslation()
  return (
    <section className="rounded-lg border border-divider-subtle bg-background-default p-6 shadow-xs">
      <h2 className="mb-4 text-sm font-medium text-text-secondary">
        {t('agent:dashboard.wallet.title')}
      </h2>
      <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
        <Metric label={t('agent:dashboard.wallet.withdrawable')} value={wallet.withdrawable} accent />
        <Metric label={t('agent:dashboard.wallet.pending')} value={wallet.pending} />
        <Metric label={t('agent:dashboard.wallet.totalEarned')} value={wallet.total_earned} />
        <Metric label={t('agent:dashboard.wallet.totalWithdrawn')} value={wallet.total_withdrawn} />
      </div>
    </section>
  )
}

export default WalletCard
