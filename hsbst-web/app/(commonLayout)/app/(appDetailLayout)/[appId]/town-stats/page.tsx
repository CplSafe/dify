'use client'

import type { EChartsOption } from 'echarts'
import dayjs from 'dayjs'
import ReactECharts from 'echarts-for-react'
import * as React from 'react'
import { useMemo, useState } from 'react'
import { useParams } from '@/next/navigation'
import { useAppTownDistribution, useAppTownTrend } from '@/service/use-apps'

const QUERY_DATE_FORMAT = 'YYYY-MM-DD HH:mm'
const TREND_TOWN_LIMIT = 6

const PERIODS = [
  { days: 7, label: '近 7 天' },
  { days: 30, label: '近 30 天' },
  { days: 90, label: '近 90 天' },
]

type Range = { start: string, end: string }

const rangeOf = (days: number, offsetDays: number): Range => {
  const end = dayjs().subtract(offsetDays, 'day').endOf('day')
  return {
    start: end.subtract(days - 1, 'day').startOf('day').format(QUERY_DATE_FORMAT),
    end: end.format(QUERY_DATE_FORMAT),
  }
}

const rangeLastYear = (days: number): Range => {
  const end = dayjs().subtract(1, 'year').endOf('day')
  return {
    start: end.subtract(days - 1, 'day').startOf('day').format(QUERY_DATE_FORMAT),
    end: end.format(QUERY_DATE_FORMAT),
  }
}

const formatDelta = (current: number, base: number) => {
  if (base === 0)
    return current > 0 ? { text: '新增', cls: 'text-util-colors-green-green-600' } : { text: '—', cls: 'text-text-quaternary' }
  const pct = ((current - base) / base) * 100
  if (Math.abs(pct) < 0.05)
    return { text: '持平', cls: 'text-text-tertiary' }
  return {
    text: `${pct > 0 ? '↑' : '↓'}${Math.abs(pct).toFixed(1)}%`,
    cls: pct > 0 ? 'text-util-colors-green-green-600' : 'text-util-colors-red-red-600',
  }
}

const TownStatsPage = () => {
  const { appId } = useParams<{ appId: string }>()
  const [days, setDays] = useState(30)

  const current = useMemo(() => rangeOf(days, 0), [days])
  const previous = useMemo(() => rangeOf(days, days), [days])
  const lastYear = useMemo(() => rangeLastYear(days), [days])

  const { data: cur, isLoading, error } = useAppTownDistribution(appId, current)
  const { data: prev } = useAppTownDistribution(appId, previous)
  const { data: yoy } = useAppTownDistribution(appId, lastYear)
  const { data: trend } = useAppTownTrend(appId, current)

  const prevMap = useMemo(
    () => new Map((prev?.data ?? []).map(r => [r.town, r.conversation_count])),
    [prev],
  )
  const yoyMap = useMemo(
    () => new Map((yoy?.data ?? []).map(r => [r.town, r.conversation_count])),
    [yoy],
  )

  const rows = useMemo(() => cur?.data ?? [], [cur])
  const unspecified = cur?.unspecified_count ?? 0
  const townTotal = rows.reduce((s, r) => s + r.conversation_count, 0)
  const total = townTotal + unspecified
  const prevTotal = (prev?.data ?? []).reduce((s, r) => s + r.conversation_count, 0) + (prev?.unspecified_count ?? 0)
  const yoyTotal = (yoy?.data ?? []).reduce((s, r) => s + r.conversation_count, 0) + (yoy?.unspecified_count ?? 0)
  const totalMoM = formatDelta(total, prevTotal)
  const totalYoY = formatDelta(total, yoyTotal)

  const barOption = useMemo<EChartsOption>(() => ({
    grid: { left: 90, right: 24, top: 16, bottom: 24 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { show: true, top: 0, right: 0, data: ['本期', '上一期'] },
    xAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map(r => r.town),
      axisLabel: { fontSize: 12 },
    },
    series: [
      {
        name: '本期',
        type: 'bar',
        data: rows.map(r => r.conversation_count),
        itemStyle: { color: '#296dff', borderRadius: [0, 4, 4, 0] },
        barMaxWidth: 14,
      },
      {
        name: '上一期',
        type: 'bar',
        data: rows.map(r => prevMap.get(r.town) ?? 0),
        itemStyle: { color: '#d1d9e0', borderRadius: [0, 4, 4, 0] },
        barMaxWidth: 14,
      },
    ],
  }), [rows, prevMap])

  const lineOption = useMemo<EChartsOption>(() => {
    const points = trend?.data ?? []
    const dates = [...new Set(points.map(p => p.date))].sort()
    const top = rows.slice(0, TREND_TOWN_LIMIT).map(r => r.town)
    const key = (d: string, t: string) => `${d}|${t}`
    const lookup = new Map(points.map(p => [key(p.date, p.town), p.conversation_count]))
    return {
      grid: { left: 40, right: 24, top: 32, bottom: 32 },
      tooltip: { trigger: 'axis' },
      legend: { show: true, top: 0, data: top },
      xAxis: { type: 'category', data: dates, boundaryGap: false },
      yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
      series: top.map(town => ({
        name: town,
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        data: dates.map(d => lookup.get(key(d, town)) ?? 0),
      })),
    }
  }, [trend, rows])

  return (
    <div className="grow overflow-auto p-6">
      <div className="mb-1 flex items-center justify-between">
        <h1 className="title-2xl-semi-bold text-text-primary">各乡镇使用情况</h1>
        <div className="flex items-center gap-1">
          {PERIODS.map(p => (
            <button
              key={p.days}
              type="button"
              onClick={() => setDays(p.days)}
              className={`h-8 rounded-lg px-3 system-sm-regular ${
                days === p.days
                  ? 'bg-components-main-nav-nav-button-bg-active text-text-primary'
                  : 'text-text-tertiary hover:bg-state-base-hover'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mb-5 body-xs-regular text-text-tertiary">
        按用户在小程序中选择的户籍地统计，非 GPS 实时定位；未填写户籍地的会话计入「未填写」，不计入任何乡镇。
        环比对比上一个同长度周期，同比对比去年同期。
      </p>

      {error && <div className="body-sm-regular text-text-destructive">加载失败，请重试。</div>}
      {isLoading && <div className="body-sm-regular text-text-tertiary">加载中…</div>}

      {!isLoading && !error && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
              <div className="body-xs-regular text-text-tertiary">总会话数</div>
              <div className="title-xl-semi-bold text-text-primary">{total}</div>
              <div className="mt-1 flex gap-3 body-xs-regular">
                <span className={totalMoM.cls}>
                  环比
                  {totalMoM.text}
                </span>
                <span className={totalYoY.cls}>
                  同比
                  {totalYoY.text}
                </span>
              </div>
            </div>
            <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
              <div className="body-xs-regular text-text-tertiary">已填写户籍地</div>
              <div className="title-xl-semi-bold text-text-primary">{townTotal}</div>
              <div className="mt-1 body-xs-regular text-text-tertiary">
                {total > 0 ? `占 ${((townTotal / total) * 100).toFixed(1)}%` : '—'}
              </div>
            </div>
            <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
              <div className="body-xs-regular text-text-tertiary">未填写</div>
              <div className="title-xl-semi-bold text-text-primary">{unspecified}</div>
              <div className="mt-1 body-xs-regular text-text-tertiary">
                {total > 0 ? `占 ${((unspecified / total) * 100).toFixed(1)}%` : '—'}
              </div>
            </div>
            <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
              <div className="body-xs-regular text-text-tertiary">覆盖乡镇</div>
              <div className="title-xl-semi-bold text-text-primary">{rows.length}</div>
              <div className="mt-1 body-xs-regular text-text-tertiary">共 18 个乡镇/街道</div>
            </div>
          </div>

          {rows.length === 0
            ? <div className="body-sm-regular text-text-tertiary">该时间段内没有带户籍地的会话。</div>
            : (
                <>
                  <div className="mb-6 rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
                    <div className="mb-2 system-md-semibold text-text-primary">乡镇排名（本期 vs 上一期）</div>
                    <ReactECharts option={barOption} style={{ height: Math.max(240, rows.length * 28) }} />
                  </div>

                  <div className="mb-6 rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
                    <div className="mb-2 system-md-semibold text-text-primary">
                      使用趋势（前
                      {' '}
                      {Math.min(TREND_TOWN_LIMIT, rows.length)}
                      {' '}
                      个乡镇）
                    </div>
                    <ReactECharts option={lineOption} style={{ height: 300 }} />
                  </div>

                  <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-4">
                    <div className="mb-2 system-md-semibold text-text-primary">明细</div>
                    <table className="w-full table-fixed">
                      <thead>
                        <tr className="border-b border-divider-subtle system-xs-medium-uppercase text-text-tertiary">
                          <th className="w-10 py-2 text-left font-normal">#</th>
                          <th className="py-2 text-left font-normal">乡镇/街道</th>
                          <th className="w-20 py-2 text-right font-normal">会话数</th>
                          <th className="w-20 py-2 text-right font-normal">用户数</th>
                          <th className="w-20 py-2 text-right font-normal">占比</th>
                          <th className="w-24 py-2 text-right font-normal">环比</th>
                          <th className="w-24 py-2 text-right font-normal">同比</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, index) => {
                          const mom = formatDelta(row.conversation_count, prevMap.get(row.town) ?? 0)
                          const yy = formatDelta(row.conversation_count, yoyMap.get(row.town) ?? 0)
                          return (
                            <tr key={row.town} className="border-b border-divider-subtle">
                              <td className="py-2 body-sm-regular text-text-quaternary">{index + 1}</td>
                              <td className="py-2 body-sm-medium text-text-primary">{row.town}</td>
                              <td className="py-2 text-right body-sm-regular text-text-secondary">{row.conversation_count}</td>
                              <td className="py-2 text-right body-sm-regular text-text-secondary">{row.user_count}</td>
                              <td className="py-2 text-right body-sm-regular text-text-tertiary">
                                {total > 0 ? `${((row.conversation_count / total) * 100).toFixed(1)}%` : '—'}
                              </td>
                              <td className={`py-2 text-right body-sm-regular ${mom.cls}`}>{mom.text}</td>
                              <td className={`py-2 text-right body-sm-regular ${yy.cls}`}>{yy.text}</td>
                            </tr>
                          )
                        })}
                        {unspecified > 0 && (
                          <tr>
                            <td className="py-2 body-sm-regular text-text-quaternary">—</td>
                            <td className="py-2 body-sm-medium text-text-tertiary">未填写户籍地</td>
                            <td className="py-2 text-right body-sm-regular text-text-tertiary">{unspecified}</td>
                            <td className="py-2 text-right body-sm-regular text-text-tertiary">{cur?.unspecified_user_count ?? 0}</td>
                            <td className="py-2 text-right body-sm-regular text-text-tertiary">
                              {total > 0 ? `${((unspecified / total) * 100).toFixed(1)}%` : '—'}
                            </td>
                            <td className="py-2 text-right body-sm-regular text-text-quaternary">—</td>
                            <td className="py-2 text-right body-sm-regular text-text-quaternary">—</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
        </>
      )}
    </div>
  )
}

export default TownStatsPage
