'use client'

import type { TrendPoint } from '@/contract/console/agent'
import * as React from 'react'
import { useTranslation } from 'react-i18next'
import dynamic from '@/next/dynamic'

// Lazy-load echarts to avoid pulling it into the layout chunk.
const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false })

type TrendChartProps = {
  trend: TrendPoint[]
}

const TrendChart = ({ trend }: TrendChartProps) => {
  const { t } = useTranslation()

  const allZero = trend.every(p => Number.parseFloat(p.consumption) === 0)

  if (trend.length === 0 || allZero) {
    return (
      <section className="rounded-lg border border-divider-subtle bg-background-default p-6 shadow-xs">
        <h2 className="mb-4 text-sm font-medium text-text-secondary">
          {t('agent:dashboard.trend.title', { days: trend.length || 7 })}
        </h2>
        <div className="flex h-48 items-center justify-center text-sm text-text-tertiary">
          {t('agent:dashboard.trend.empty')}
        </div>
      </section>
    )
  }

  const dates = trend.map(p => p.date)
  const values = trend.map(p => Number.parseFloat(p.consumption))

  const option = {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 24, bottom: 24 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { formatter: (v: string) => v.slice(5) /* MM-DD */ },
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: t('agent:dashboard.trend.consumption'),
        type: 'line',
        smooth: true,
        data: values,
        areaStyle: { opacity: 0.15 },
      },
    ],
  }

  return (
    <section className="rounded-lg border border-divider-subtle bg-background-default p-6 shadow-xs">
      <h2 className="mb-4 text-sm font-medium text-text-secondary">
        {t('agent:dashboard.trend.title', { days: trend.length })}
      </h2>
      <ReactECharts option={option} style={{ height: 240 }} />
    </section>
  )
}

export default TrendChart
