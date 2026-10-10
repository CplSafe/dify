'use client'

import type { EChartsOption } from 'echarts'
import type { AppTownDistributionResponse, AppTownTrendResponse } from '@/models/app'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import ReactECharts from 'echarts-for-react'
import * as React from 'react'
import { useMemo, useState } from 'react'
import { useParams } from '@/next/navigation'
import { get, getPublic } from '@/service/base'
import { TownStatsDetailPanel } from './detail-panel'

const QUERY_DATE_FORMAT = 'YYYY-MM-DD HH:mm'
const DISPLAY_DATE_FORMAT = 'YYYY/M/D'
const TREND_TOWN_LIMIT = 6
const VILLAGE_RANKING_LIMIT = 20

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
type TownStatsSource = 'console' | 'public'
type RankingLevel = 'town' | 'village'

const useTownStatistic = <T,>(source: TownStatsSource, appId: string | undefined, metric: string, params: Range) => {
  return useQuery<T>({
    queryKey: ['town-statistics', source, metric, appId, params],
    queryFn: () => source === 'public'
      ? getPublic<T>(`/town-statistics/${metric}`, { params })
      : get<T>(`/apps/${appId}/statistics/town-${metric}`, { params }),
    enabled: source === 'public' || !!appId,
  })
}

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

type TownStatsProps = {
  appId?: string
  source?: TownStatsSource
}

export const TownStats = ({ appId: appIdProp, source = 'console' }: TownStatsProps) => {
  const { appId: routeAppId } = useParams<{ appId?: string }>()
  const appId = appIdProp || routeAppId
  const [days, setDays] = useState(30)
  const [rankingLevel, setRankingLevel] = useState<RankingLevel>('town')
  const [rankingTown, setRankingTown] = useState('')
  const [trendLevel, setTrendLevel] = useState<RankingLevel>('town')
  const [trendTown, setTrendTown] = useState('')

  const current = useMemo(() => rangeOf(days, 0), [days])
  const previous = useMemo(() => rangeOf(days, days), [days])
  const lastYear = useMemo(() => rangeLastYear(days), [days])

  const { data: cur, isLoading, error } = useTownStatistic<AppTownDistributionResponse>(source, appId, 'distribution', current)
  const { data: prev } = useTownStatistic<AppTownDistributionResponse>(source, appId, 'distribution', previous)
  const { data: yoy } = useTownStatistic<AppTownDistributionResponse>(source, appId, 'distribution', lastYear)
  const { data: trend } = useTownStatistic<AppTownTrendResponse>(source, appId, 'trend', current)

  const rows = useMemo(() => cur?.data ?? [], [cur])
  const villageRows = useMemo(() => cur?.villages ?? [], [cur])
  const prevMap = useMemo(() => new Map((prev?.data ?? []).map(r => [r.town, r.conversation_count])), [prev])
  const yoyMap = useMemo(() => new Map((yoy?.data ?? []).map(r => [r.town, r.conversation_count])), [yoy])
  const previousVillageMap = useMemo(() => new Map(
    (prev?.villages ?? []).map(row => [`${row.town}|:${row.village}`, row.conversation_count]),
  ), [prev])

  const rankingRows = useMemo(() => {
    if (rankingLevel === 'town') {
      return rows.map(row => ({
        key: row.town,
        label: row.town,
        current: row.conversation_count,
        previous: prevMap.get(row.town) ?? 0,
      }))
    }
    return villageRows
      .filter(row => !rankingTown || row.town === rankingTown)
      .slice(0, VILLAGE_RANKING_LIMIT)
      .map((row) => {
        const key = `${row.town}|:${row.village}`
        return {
          key,
          label: row.village,
          current: row.conversation_count,
          previous: previousVillageMap.get(key) ?? 0,
        }
      })
  }, [prevMap, previousVillageMap, rankingLevel, rankingTown, rows, villageRows])

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
      data: rankingRows.map(row => row.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#1F2A37', fontSize: 12 },
    },
    series: [
      {
        name: '本期',
        type: 'bar',
        data: rankingRows.map(row => row.current),
        itemStyle: { color: BAR_CURRENT, borderRadius: [0, 3, 3, 0] },
        barMaxWidth: 12,
        label: { show: true, position: 'right', color: AXIS_LABEL, fontSize: 12 },
      },
      {
        name: '上一期',
        type: 'bar',
        data: rankingRows.map(row => row.previous),
        itemStyle: { color: BAR_PREVIOUS, borderRadius: [0, 3, 3, 0] },
        barMaxWidth: 12,
      },
    ],
  }), [rankingRows])

  const lineOption = useMemo<EChartsOption>(() => {
    const points = trendLevel === 'town' ? (trend?.data ?? []) : (trend?.villages ?? [])
    const dates = [...new Set(points.map(p => p.date))].sort()
    const top = trendLevel === 'town'
      ? rows.slice(0, TREND_TOWN_LIMIT).map(row => ({ key: row.town, label: row.town }))
      : villageRows
          .filter(row => !trendTown || row.town === trendTown)
          .slice(0, TREND_TOWN_LIMIT)
          .map(row => ({ key: `${row.town}|:${row.village}`, label: row.village }))
    const pointKey = (point: (typeof points)[number]) => trendLevel === 'town'
      ? point.town
      : `${point.town}|:${'village' in point ? point.village : ''}`
    const lookup = new Map(points.map(point => [`${point.date}|${pointKey(point)}`, point.conversation_count]))
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
      series: top.map(item => ({
        name: item.label,
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        data: dates.map(date => lookup.get(`${date}|${item.key}`) ?? 0),
      })),
    }
  }, [trend, trendLevel, trendTown, rows, villageRows])

  const trendSeriesCount = trendLevel === 'town'
    ? Math.min(TREND_TOWN_LIMIT, rows.length)
    : Math.min(TREND_TOWN_LIMIT, villageRows.filter(row => !trendTown || row.town === trendTown).length)

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
                hint={`已统计 ${villageRows.length} 个村/社区`}
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
                    <Panel title="区域排名" subtitle="深色为本期，浅色为上一周期">
                      <div className="mb-4 flex flex-col gap-3 border-b border-divider-subtle pb-4 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex w-fit items-center gap-1 rounded-lg bg-background-section p-1" aria-label="排名统计层级">
                          <button
                            type="button"
                            onClick={() => setRankingLevel('town')}
                            className={`h-8 rounded-md px-3 system-sm-medium transition-colors ${
                              rankingLevel === 'town'
                                ? 'bg-components-panel-bg text-text-primary shadow-xs'
                                : 'text-text-tertiary hover:text-text-secondary'
                            }`}
                          >
                            乡镇/街道
                          </button>
                          <button
                            type="button"
                            onClick={() => setRankingLevel('village')}
                            className={`h-8 rounded-md px-3 system-sm-medium transition-colors ${
                              rankingLevel === 'village'
                                ? 'bg-components-panel-bg text-text-primary shadow-xs'
                                : 'text-text-tertiary hover:text-text-secondary'
                            }`}
                          >
                            村/社区
                          </button>
                        </div>
                        {rankingLevel === 'village' && (
                          <select
                            aria-label="排名按乡镇/街道筛选"
                            value={rankingTown}
                            onChange={event => setRankingTown(event.target.value)}
                            className="h-8 min-w-0 rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-2.5 system-sm-regular text-text-secondary outline-none sm:w-48"
                          >
                            <option value="">全部乡镇/街道</option>
                            {rows.map(row => <option key={row.town} value={row.town}>{row.town}</option>)}
                          </select>
                        )}
                      </div>
                      {rankingLevel === 'village' && (
                        <div className="mb-2 system-xs-regular text-text-tertiary">
                          {rankingTown ? `${rankingTown}村/社区会话量前 ${VILLAGE_RANKING_LIMIT} 名` : `全区村/社区会话量前 ${VILLAGE_RANKING_LIMIT} 名`}
                        </div>
                      )}
                      {rankingRows.length > 0
                        ? (
                            <ReactECharts
                              option={barOption}
                              style={{ height: Math.max(260, rankingRows.length * 30) }}
                              opts={{ renderer: 'svg' }}
                            />
                          )
                        : (
                            <div className="flex min-h-40 items-center justify-center body-sm-regular text-text-tertiary">
                              该条件下暂无排名数据。
                            </div>
                          )}
                    </Panel>

                    <Panel
                      title="使用趋势"
                      subtitle={`会话量排名前 ${trendSeriesCount} 的${trendLevel === 'town' ? '乡镇/街道' : '村/社区'}`}
                    >
                      <div className="mb-4 flex flex-col gap-3 border-b border-divider-subtle pb-4 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex w-fit items-center gap-1 rounded-lg bg-background-section p-1" aria-label="趋势统计层级">
                          <button
                            type="button"
                            onClick={() => setTrendLevel('town')}
                            className={`h-8 rounded-md px-3 system-sm-medium transition-colors ${
                              trendLevel === 'town'
                                ? 'bg-components-panel-bg text-text-primary shadow-xs'
                                : 'text-text-tertiary hover:text-text-secondary'
                            }`}
                          >
                            乡镇/街道
                          </button>
                          <button
                            type="button"
                            onClick={() => setTrendLevel('village')}
                            className={`h-8 rounded-md px-3 system-sm-medium transition-colors ${
                              trendLevel === 'village'
                                ? 'bg-components-panel-bg text-text-primary shadow-xs'
                                : 'text-text-tertiary hover:text-text-secondary'
                            }`}
                          >
                            村/社区
                          </button>
                        </div>
                        {trendLevel === 'village' && (
                          <select
                            aria-label="趋势按乡镇/街道筛选"
                            value={trendTown}
                            onChange={event => setTrendTown(event.target.value)}
                            className="h-8 min-w-0 rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-2.5 system-sm-regular text-text-secondary outline-none sm:w-48"
                          >
                            <option value="">全部乡镇/街道</option>
                            {rows.map(row => <option key={row.town} value={row.town}>{row.town}</option>)}
                          </select>
                        )}
                      </div>
                      <ReactECharts option={lineOption} style={{ height: 300 }} opts={{ renderer: 'svg' }} />
                    </Panel>

                    <Panel title="区域明细" subtitle="切换统计层级，并按乡镇或村/社区筛选">
                      <TownStatsDetailPanel
                        towns={rows}
                        villages={villageRows}
                        total={total}
                        unspecifiedCount={unspecified}
                        unspecifiedUserCount={cur?.unspecified_user_count ?? 0}
                        previousTownCounts={prevMap}
                        lastYearTownCounts={yoyMap}
                      />
                    </Panel>

                    <div className="pb-2 system-xs-regular text-text-quaternary">
                      说明：统计口径为用户在小程序中选择的户籍地，非 GPS 实时定位。
                      未填写户籍地的会话单列，不计入任何乡镇；只填写乡镇的记录计入乡镇汇总，不进入村/社区明细。
                      环比对比上一个同长度周期，同比对比去年同期。
                    </div>
                  </div>
                )}
          </>
        )}
      </div>
    </div>
  )
}

export default TownStats
