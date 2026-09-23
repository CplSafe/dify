'use client'

import dayjs from 'dayjs'
import * as React from 'react'
import { useMemo, useState } from 'react'
import { useAppList, useAppTownDistribution } from '@/service/use-apps'

const QUERY_DATE_FORMAT = 'YYYY-MM-DD HH:mm'

const PERIODS = [
  { days: 7, label: '近 7 天' },
  { days: 30, label: '近 30 天' },
  { days: 90, label: '近 90 天' },
  { days: 0, label: '全部' },
]

const StatsPage = () => {
  const [appId, setAppId] = useState('')
  const [days, setDays] = useState(30)

  const { data: appList, isLoading: isAppListLoading } = useAppList({ page: 1, limit: 100 })
  const apps = appList?.data ?? []
  const activeAppId = appId || apps[0]?.id || ''

  const params = useMemo(() => {
    if (days === 0)
      return undefined
    return {
      start: dayjs().subtract(days, 'day').startOf('day').format(QUERY_DATE_FORMAT),
      end: dayjs().endOf('day').format(QUERY_DATE_FORMAT),
    }
  }, [days])

  const { data, isLoading, error } = useAppTownDistribution(activeAppId, params)

  const rows = data?.data ?? []
  const unspecified = data?.unspecified_count ?? 0
  const townTotal = rows.reduce((sum, row) => sum + row.conversation_count, 0)
  const total = townTotal + unspecified
  const maxCount = rows.reduce((max, row) => Math.max(max, row.conversation_count), 0)

  return (
    <div className="grow overflow-auto p-6">
      <h1 className="mb-1 title-2xl-semi-bold text-text-primary">各乡镇使用情况</h1>
      <p className="mb-5 body-xs-regular text-text-tertiary">
        按用户在小程序中选择的户籍地统计，非 GPS 实时定位；未选择户籍地的会话计入「未填写」，不计入任何乡镇。
      </p>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <select
          className="h-8 rounded-lg border border-components-input-border-active bg-components-input-bg-normal px-2 system-sm-regular text-text-primary"
          value={activeAppId}
          onChange={e => setAppId(e.target.value)}
        >
          {isAppListLoading && <option value="">加载中…</option>}
          {apps.map(app => (
            <option key={app.id} value={app.id}>{app.name}</option>
          ))}
        </select>

        <div className="flex items-center gap-1">
          {PERIODS.map(period => (
            <button
              key={period.days}
              type="button"
              onClick={() => setDays(period.days)}
              className={`h-8 rounded-lg px-3 system-sm-regular ${
                days === period.days
                  ? 'bg-components-main-nav-nav-button-bg-active text-text-primary'
                  : 'text-text-tertiary hover:bg-state-base-hover'
              }`}
            >
              {period.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="body-sm-regular text-text-destructive">加载失败，请重试。</div>}
      {isLoading && <div className="body-sm-regular text-text-tertiary">加载中…</div>}

      {!isLoading && !error && (
        <>
          <div className="mb-4 flex gap-6">
            <div>
              <div className="body-xs-regular text-text-tertiary">总会话数</div>
              <div className="title-xl-semi-bold text-text-primary">{total}</div>
            </div>
            <div>
              <div className="body-xs-regular text-text-tertiary">已填写户籍地</div>
              <div className="title-xl-semi-bold text-text-primary">{townTotal}</div>
            </div>
            <div>
              <div className="body-xs-regular text-text-tertiary">未填写</div>
              <div className="title-xl-semi-bold text-text-primary">{unspecified}</div>
            </div>
            <div>
              <div className="body-xs-regular text-text-tertiary">覆盖乡镇</div>
              <div className="title-xl-semi-bold text-text-primary">{rows.length}</div>
            </div>
          </div>

          {rows.length === 0
            ? <div className="body-sm-regular text-text-tertiary">该时间段内没有带户籍地的会话。</div>
            : (
                <table className="w-full table-fixed">
                  <thead>
                    <tr className="border-b border-divider-subtle system-xs-medium-uppercase text-text-tertiary">
                      <th className="w-10 py-2 text-left font-normal">#</th>
                      <th className="py-2 text-left font-normal">乡镇/街道</th>
                      <th className="w-24 py-2 text-right font-normal">会话数</th>
                      <th className="w-24 py-2 text-right font-normal">用户数</th>
                      <th className="w-20 py-2 text-right font-normal">占比</th>
                      <th className="w-40 py-2 pl-4 text-left font-normal">分布</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={row.town} className="border-b border-divider-subtle">
                        <td className="py-2 body-sm-regular text-text-quaternary">{index + 1}</td>
                        <td className="py-2 body-sm-medium text-text-primary">{row.town}</td>
                        <td className="py-2 text-right body-sm-regular text-text-secondary">{row.conversation_count}</td>
                        <td className="py-2 text-right body-sm-regular text-text-secondary">{row.user_count}</td>
                        <td className="py-2 text-right body-sm-regular text-text-tertiary">
                          {total > 0 ? `${((row.conversation_count / total) * 100).toFixed(1)}%` : '—'}
                        </td>
                        <td className="py-2 pl-4">
                          <div className="h-2 w-full rounded-full bg-background-section">
                            <div
                              className="h-2 rounded-full bg-components-progress-brand-progress"
                              style={{ width: maxCount > 0 ? `${(row.conversation_count / maxCount) * 100}%` : '0%' }}
                            />
                          </div>
                        </td>
                      </tr>
                    ))}
                    {unspecified > 0 && (
                      <tr>
                        <td className="py-2 body-sm-regular text-text-quaternary">—</td>
                        <td className="py-2 body-sm-medium text-text-tertiary">未填写户籍地</td>
                        <td className="py-2 text-right body-sm-regular text-text-tertiary">{unspecified}</td>
                        <td className="py-2 text-right body-sm-regular text-text-tertiary">{data?.unspecified_user_count ?? 0}</td>
                        <td className="py-2 text-right body-sm-regular text-text-tertiary">
                          {total > 0 ? `${((unspecified / total) * 100).toFixed(1)}%` : '—'}
                        </td>
                        <td className="py-2 pl-4" />
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
        </>
      )}
    </div>
  )
}

export default StatsPage
