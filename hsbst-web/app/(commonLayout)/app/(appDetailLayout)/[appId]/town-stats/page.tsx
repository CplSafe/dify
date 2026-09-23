'use client'

import type { EChartsOption } from 'echarts'
import dayjs from 'dayjs'
import ReactECharts from 'echarts-for-react'
import * as React from 'react'
import { useMemo, useState } from 'react'
import { useParams } from '@/next/navigation'
import { useAppTownDistribution, useAppTownTrend } from '@/service/use-apps'

const QUERY_DATE_FORMAT = 'YYYY-MM-DD HH:mm'
const DISPLAY_DATE_FORMAT = 'YYYY/M/D'
const TREND_TOWN_LIMIT = 6

const AXIS_LABEL = '#9CA3AF'
const SPLIT_LINE = '#F3F4F6'
const BAR_CURRENT = '#1C64F2'
const BAR_PREVIOUS = '#E5E7EB'
const LINE_COLORS = ['#1C64F2', '#0E9F6E', '#FF8A4C', '#9061F9', '#E74694', '#16BDCA']

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

const labelOf = (range: Range) =>
  `${dayjs(range.start).format(DISPLAY_DATE_FORMAT)} — ${dayjs(range.end).format(DISPLAY_DATE_FORMAT)}`

type Delta = { text: string, cls: string }

const deltaOf = (current: number, base: number): Delta => {
  if (base === 0) {
    return current > 0
      ? { text: '新增', cls: 'text-util-colors-green-green-600' }
      : { text: '—', cls: 'text-text-quaternary' }
  }
  const pct = ((current - base) / base) * 100
  if (Math.abs(pct) < 0.05)
    return { text: '持平', cls: 'text-text-tertiary' }
  return {
    text: `${pct > 0 ? '+' : '-'}${Math.abs(pct).toFixed(1)}%`,
    cls: pct > 0 ? 'text-util-colors-green-green-600' : 'text-util-colors-red-red-600',
  }
}

type MetricCardProps = {
  label: string
  value: number
  hint?: string
  mom?: Delta
  yoy?: Delta
}

const MetricCard = ({ label, value, hint, mom, yoy }: MetricCardProps) => (
  <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-5">
    <div className="system-xs-medium-uppercase text-text-tertiary">{label}</div>
    <div className="mt-2 text-[32px] leading-none font-semibold text-text-primary tabular-nums">
      {value.toLocaleString()}
    </div>
    {(mom || yoy) && (
      <div className="mt-3 flex gap-4 system-xs-regular">
        {mom && (
          <span className="text-text-tertiary">
            环比
            <span className={mom.cls}>{mom.text}</span>
          </span>
        )}
        {yoy && (
          <span className="text-text-tertiary">
            同比
            <span className={yoy.cls}>{yoy.text}</span>
          </span>
        )}
      </div>
    )}
    {hint && !mom && <div className="mt-3 system-xs-regular text-text-tertiary">{hint}</div>}
  </div>
)

const Panel = ({ title, subtitle, children }: { title: string, subtitle?: string, children: React.ReactNode }) => (
  <div className="rounded-xl border border-divider-subtle bg-components-panel-bg p-5">
    <div className="mb-4">
      <div className="system-md-semibold text-text-primary">{title}</div>
      {subtitle && <div className="mt-0.5 system-xs-regular text-text-tertiary">{subtitle}</div>}
    </div>
    {children}
  </div>
)

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

  const rows = useMemo(() => cur?.data ?? [], [cur])
  const prevMap = useMemo(() => new Map((prev?.data ?? []).map(r => [r.town, r.conversation_count])), [prev])
  const yoyMap = useMemo(() => new Map((yoy?.data ?? []).map(r => [r.town, r.conversation_count])), [yoy])

  const unspecified = cur?.unspecified_count ?? 0
  const townTotal = rows.reduce((s, r) => s + r.conversation_count, 0)
  const total = townTotal + unspecified
  const userTotal = rows.reduce((s, r) => s + r.user_count, 0)
  const prevTotal = (prev?.data ?? []).reduce((s, r) => s + r.conversation_count, 0) + (prev?.unspecified_count ?? 0)
  const yoyTotal = (yoy?.data ?? []).reduce((s, r) => s + r.conversation_count, 0) + (yoy?.unspecified_count ?? 0)

  const barOption = useMemo<EChartsOption>(() => ({
    grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: '#E5E7EB',
      textStyle: { color: '#1F2A37', fontSize: 12 },
    },
    legend: { show: true, top: 0, right: 0, itemWidth: 8, itemHeight: 8, textStyle: { color: AXIS_LABEL, fontSize: 12 } },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: AXIS_LABEL, fontSize: 12 },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: rows.map(r => r.town),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#1F2A37', fontSize: 12 },
    },
    series: [
      {
        name: '本期',
        type: 'bar',
        data: rows.map(r => r.conversation_count),
        itemStyle: { color: BAR_CURRENT, borderRadius: [0, 3, 3, 0] },
        barMaxWidth: 12,
        label: { show: true, position: 'right', color: AXIS_LABEL, fontSize: 12 },
      },
      {
        name: '上一期',
        type: 'bar',
        data: rows.map(r => prevMap.get(r.town) ?? 0),
        itemStyle: { color: BAR_PREVIOUS, borderRadius: [0, 3, 3, 0] },
        barMaxWidth: 12,
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
      color: LINE_COLORS,
      grid: { left: 8, right: 16, top: 32, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#fff',
        borderColor: '#E5E7EB',
        textStyle: { color: '#1F2A37', fontSize: 12 },
      },
      legend: { show: true, top: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: AXIS_LABEL, fontSize: 12 } },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: AXIS_LABEL, fontSize: 12, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: AXIS_LABEL, fontSize: 12 },
        splitLine: { lineStyle: { color: SPLIT_LINE } },
      },
      series: top.map(town => ({
        name: town,
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        data: dates.map(d => lookup.get(key(d, town)) ?? 0),
      })),
    }
  }, [trend, rows])

  return (
    <div className="h-full overflow-y-auto bg-chatbot-bg px-4 py-6 sm:px-12">
      <div className="mx-auto max-w-[1200px]">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
          <h1 className="title-2xl-semi-bold text-text-primary">各乡镇使用情况</h1>
          <div className="flex items-center gap-1 rounded-lg bg-components-panel-bg p-1">
            {PERIODS.map(p => (
              <button
                key={p.days}
                type="button"
                onClick={() => setDays(p.days)}
                className={`h-7 rounded-md px-3 system-sm-regular transition-colors ${
                  days === p.days
                    ? 'bg-components-main-nav-nav-button-bg-active text-text-primary shadow-xs'
                    : 'text-text-tertiary hover:text-text-secondary'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className="mb-6 system-xs-regular text-text-tertiary">
          统计周期
          {' '}
          {labelOf(current)}
          · 环比
          {' '}
          {labelOf(previous)}
          · 同比
          {' '}
          {labelOf(lastYear)}
        </div>

        {error && <div className="body-sm-regular text-text-destructive">数据加载失败，请刷新重试。</div>}
        {isLoading && <div className="body-sm-regular text-text-tertiary">加载中…</div>}

        {!isLoading && !error && (
          <>
            <div className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
              <MetricCard
                label="总会话数"
                value={total}
                mom={deltaOf(total, prevTotal)}
                yoy={deltaOf(total, yoyTotal)}
              />
              <MetricCard
                label="覆盖乡镇"
                value={rows.length}
                hint="共 18 个乡镇/街道"
              />
              <MetricCard
                label="咨询用户数"
                value={userTotal}
                hint="已填写户籍地的去重用户"
              />
              <MetricCard
                label="未填写户籍地"
                value={unspecified}
                hint={total > 0 ? `占总会话 ${((unspecified / total) * 100).toFixed(1)}%` : '—'}
              />
            </div>

            {rows.length === 0
              ? (
                  <Panel title="暂无数据">
                    <div className="body-sm-regular text-text-tertiary">该统计周期内没有带户籍地的会话记录。</div>
                  </Panel>
                )
              : (
                  <div className="flex flex-col gap-4">
                    <Panel title="乡镇排名" subtitle="深色为本期，浅色为上一周期">
                      <ReactECharts
                        option={barOption}
                        style={{ height: Math.max(260, rows.length * 30) }}
                        opts={{ renderer: 'svg' }}
                      />
                    </Panel>

                    <Panel
                      title="使用趋势"
                      subtitle={`会话量排名前 ${Math.min(TREND_TOWN_LIMIT, rows.length)} 的乡镇/街道`}
                    >
                      <ReactECharts option={lineOption} style={{ height: 300 }} opts={{ renderer: 'svg' }} />
                    </Panel>

                    <Panel title="分乡镇明细">
                      <table className="w-full table-fixed">
                        <thead>
                          <tr className="border-b border-divider-regular system-xs-medium-uppercase text-text-tertiary">
                            <th className="w-12 py-2.5 text-left font-normal">排名</th>
                            <th className="py-2.5 text-left font-normal">乡镇/街道</th>
                            <th className="w-24 py-2.5 text-right font-normal">会话数</th>
                            <th className="w-24 py-2.5 text-right font-normal">用户数</th>
                            <th className="w-20 py-2.5 text-right font-normal">占比</th>
                            <th className="w-24 py-2.5 text-right font-normal">环比</th>
                            <th className="w-24 py-2.5 text-right font-normal">同比</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row, index) => {
                            const mom = deltaOf(row.conversation_count, prevMap.get(row.town) ?? 0)
                            const yy = deltaOf(row.conversation_count, yoyMap.get(row.town) ?? 0)
                            return (
                              <tr key={row.town} className="border-b border-divider-subtle hover:bg-state-base-hover">
                                <td className="py-2.5 body-sm-regular text-text-quaternary tabular-nums">{index + 1}</td>
                                <td className="py-2.5 body-sm-medium text-text-primary">{row.town}</td>
                                <td className="py-2.5 text-right body-sm-regular text-text-secondary tabular-nums">{row.conversation_count}</td>
                                <td className="py-2.5 text-right body-sm-regular text-text-secondary tabular-nums">{row.user_count}</td>
                                <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">
                                  {total > 0 ? `${((row.conversation_count / total) * 100).toFixed(1)}%` : '—'}
                                </td>
                                <td className={`py-2.5 text-right body-sm-regular tabular-nums ${mom.cls}`}>{mom.text}</td>
                                <td className={`py-2.5 text-right body-sm-regular tabular-nums ${yy.cls}`}>{yy.text}</td>
                              </tr>
                            )
                          })}
                          {unspecified > 0 && (
                            <tr className="bg-background-section-burn">
                              <td className="py-2.5 body-sm-regular text-text-quaternary">—</td>
                              <td className="py-2.5 body-sm-medium text-text-tertiary">未填写户籍地</td>
                              <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">{unspecified}</td>
                              <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">{cur?.unspecified_user_count ?? 0}</td>
                              <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">
                                {total > 0 ? `${((unspecified / total) * 100).toFixed(1)}%` : '—'}
                              </td>
                              <td className="py-2.5 text-right body-sm-regular text-text-quaternary">—</td>
                              <td className="py-2.5 text-right body-sm-regular text-text-quaternary">—</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </Panel>

                    <div className="pb-2 system-xs-regular text-text-quaternary">
                      说明：统计口径为用户在小程序中选择的户籍地，非 GPS 实时定位。
                      未填写户籍地的会话单列，不计入任何乡镇。环比对比上一个同长度周期，同比对比去年同期。
                    </div>
                  </div>
                )}
          </>
        )}
      </div>
    </div>
  )
}

export default TownStatsPage
