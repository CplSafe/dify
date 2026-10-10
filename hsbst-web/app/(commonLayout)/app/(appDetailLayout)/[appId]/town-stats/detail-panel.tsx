'use client'

import type { AppTownDistributionResponse } from '@/models/app'
import { useMemo, useState } from 'react'

type TownRow = AppTownDistributionResponse['data'][number]
type VillageRow = AppTownDistributionResponse['villages'][number]
type DetailLevel = 'town' | 'village'

type DetailPanelProps = {
  towns: TownRow[]
  villages: VillageRow[]
  total: number
  unspecifiedCount: number
  unspecifiedUserCount: number
  previousTownCounts: Map<string, number>
  lastYearTownCounts: Map<string, number>
}

const deltaOf = (current: number, base: number) => {
  if (base === 0) {
    return current > 0
      ? { text: '新增', className: 'text-util-colors-green-green-600' }
      : { text: '—', className: 'text-text-quaternary' }
  }
  const percentage = ((current - base) / base) * 100
  if (Math.abs(percentage) < 0.05)
    return { text: '持平', className: 'text-text-tertiary' }
  return {
    text: `${percentage > 0 ? '+' : '-'}${Math.abs(percentage).toFixed(1)}%`,
    className: percentage > 0 ? 'text-util-colors-green-green-600' : 'text-util-colors-red-red-600',
  }
}

export const TownStatsDetailPanel = ({
  towns,
  villages,
  total,
  unspecifiedCount,
  unspecifiedUserCount,
  previousTownCounts,
  lastYearTownCounts,
}: DetailPanelProps) => {
  const [level, setLevel] = useState<DetailLevel>('village')
  const [selectedTown, setSelectedTown] = useState('')
  const [keyword, setKeyword] = useState('')

  const filteredVillages = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLocaleLowerCase()
    return villages.filter(row => (
      (!selectedTown || row.town === selectedTown)
      && (!normalizedKeyword || row.village.toLocaleLowerCase().includes(normalizedKeyword))
    ))
  }, [keyword, selectedTown, villages])

  return (
    <>
      <div className="mb-4 flex flex-col gap-3 border-b border-divider-subtle pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex w-fit items-center gap-1 rounded-lg bg-background-section p-1" aria-label="统计层级">
          <button
            type="button"
            onClick={() => setLevel('town')}
            className={`h-8 rounded-md px-3 system-sm-medium transition-colors ${
              level === 'town'
                ? 'bg-components-panel-bg text-text-primary shadow-xs'
                : 'text-text-tertiary hover:text-text-secondary'
            }`}
          >
            乡镇/街道
          </button>
          <button
            type="button"
            onClick={() => setLevel('village')}
            className={`h-8 rounded-md px-3 system-sm-medium transition-colors ${
              level === 'village'
                ? 'bg-components-panel-bg text-text-primary shadow-xs'
                : 'text-text-tertiary hover:text-text-secondary'
            }`}
          >
            村/社区
          </button>
        </div>

        {level === 'village' && (
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
            <select
              aria-label="按乡镇/街道筛选"
              value={selectedTown}
              onChange={event => setSelectedTown(event.target.value)}
              className="h-8 min-w-0 rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-2.5 system-sm-regular text-text-secondary outline-none focus:border-components-input-border-active sm:w-44"
            >
              <option value="">全部乡镇/街道</option>
              {towns.map(row => <option key={row.town} value={row.town}>{row.town}</option>)}
            </select>
            <label className="flex h-8 min-w-0 items-center gap-2 rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-2.5 focus-within:border-components-input-border-active sm:w-52">
              <span className="i-ri-search-line size-4 shrink-0 text-text-quaternary" aria-hidden="true" />
              <span className="sr-only">搜索村/社区</span>
              <input
                value={keyword}
                onChange={event => setKeyword(event.target.value)}
                placeholder="搜索村/社区"
                className="min-w-0 flex-1 bg-transparent system-sm-regular text-text-primary outline-none placeholder:text-text-quaternary"
              />
            </label>
          </div>
        )}
      </div>

      {level === 'town'
        ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] table-fixed">
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
                  {towns.map((row, index) => {
                    const monthDelta = deltaOf(row.conversation_count, previousTownCounts.get(row.town) ?? 0)
                    const yearDelta = deltaOf(row.conversation_count, lastYearTownCounts.get(row.town) ?? 0)
                    return (
                      <tr key={row.town} className="border-b border-divider-subtle hover:bg-state-base-hover">
                        <td className="py-2.5 body-sm-regular text-text-quaternary tabular-nums">{index + 1}</td>
                        <td className="py-2.5 body-sm-medium text-text-primary">{row.town}</td>
                        <td className="py-2.5 text-right body-sm-regular text-text-secondary tabular-nums">{row.conversation_count}</td>
                        <td className="py-2.5 text-right body-sm-regular text-text-secondary tabular-nums">{row.user_count}</td>
                        <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">
                          {total > 0 ? `${((row.conversation_count / total) * 100).toFixed(1)}%` : '—'}
                        </td>
                        <td className={`py-2.5 text-right body-sm-regular tabular-nums ${monthDelta.className}`}>{monthDelta.text}</td>
                        <td className={`py-2.5 text-right body-sm-regular tabular-nums ${yearDelta.className}`}>{yearDelta.text}</td>
                      </tr>
                    )
                  })}
                  {unspecifiedCount > 0 && (
                    <tr className="bg-background-section-burn">
                      <td className="py-2.5 body-sm-regular text-text-quaternary">—</td>
                      <td className="py-2.5 body-sm-medium text-text-tertiary">未填写户籍地</td>
                      <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">{unspecifiedCount}</td>
                      <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">{unspecifiedUserCount}</td>
                      <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">
                        {total > 0 ? `${((unspecifiedCount / total) * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td className="py-2.5 text-right body-sm-regular text-text-quaternary">—</td>
                      <td className="py-2.5 text-right body-sm-regular text-text-quaternary">—</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )
        : (
            <>
              <div className="mb-2 system-xs-regular text-text-tertiary">
                共
                {' '}
                {filteredVillages.length}
                {' '}
                个村/社区
              </div>
              {filteredVillages.length === 0
                ? (
                    <div className="flex min-h-28 items-center justify-center body-sm-regular text-text-tertiary">
                      没有找到符合条件的村/社区。
                    </div>
                  )
                : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[640px] table-fixed">
                        <thead>
                          <tr className="border-b border-divider-regular system-xs-medium-uppercase text-text-tertiary">
                            <th className="w-12 py-2.5 text-left font-normal">排名</th>
                            <th className="py-2.5 text-left font-normal">乡镇/街道</th>
                            <th className="py-2.5 text-left font-normal">村/社区</th>
                            <th className="w-24 py-2.5 text-right font-normal">会话数</th>
                            <th className="w-24 py-2.5 text-right font-normal">用户数</th>
                            <th className="w-20 py-2.5 text-right font-normal">占比</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredVillages.map((row, index) => (
                            <tr key={`${row.town}-${row.village}`} className="border-b border-divider-subtle hover:bg-state-base-hover">
                              <td className="py-2.5 body-sm-regular text-text-quaternary tabular-nums">{index + 1}</td>
                              <td className="py-2.5 body-sm-regular text-text-secondary">{row.town}</td>
                              <td className="py-2.5 body-sm-medium text-text-primary">{row.village}</td>
                              <td className="py-2.5 text-right body-sm-regular text-text-secondary tabular-nums">{row.conversation_count}</td>
                              <td className="py-2.5 text-right body-sm-regular text-text-secondary tabular-nums">{row.user_count}</td>
                              <td className="py-2.5 text-right body-sm-regular text-text-tertiary tabular-nums">
                                {total > 0 ? `${((row.conversation_count / total) * 100).toFixed(1)}%` : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
            </>
          )}
    </>
  )
}
