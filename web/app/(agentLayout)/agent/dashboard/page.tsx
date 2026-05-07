'use client'

import * as React from 'react'
import { useTranslation } from 'react-i18next'
import TrendChart from '@/app/components/agent/trend-chart'
import WalletCard from '@/app/components/agent/wallet-card'
import { useAgentDashboard } from '@/service/use-agent'

const AgentDashboardPage = () => {
  const { t } = useTranslation()
  const { data, isLoading, error } = useAgentDashboard(7)

  if (isLoading) {
    return <div className="p-6 text-sm text-text-tertiary">Loading...</div>
  }

  if (error || !data) {
    return (
      <div className="text-state-destructive-text p-6 text-sm">
        {String(error?.message ?? 'Failed to load dashboard')}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-xl font-semibold text-text-primary">
        {t('agent:dashboard.title')}
      </h1>
      <WalletCard wallet={data.wallet} />
      <TrendChart trend={data.trend} />
    </div>
  )
}

export default AgentDashboardPage
