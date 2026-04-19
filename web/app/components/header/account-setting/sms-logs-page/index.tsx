'use client'

import { useCallback, useEffect, useState } from 'react'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { get } from '@/service/base'

type SmsLog = {
  id: string
  phone: string
  code: string
  purpose: string
  sent_at: string | null
}

type SmsLogsResponse = {
  total: number
  page: number
  per_page: number
  items: SmsLog[]
}

const PURPOSE_LABELS: Record<string, string> = {
  login_verify: '登录验证',
  invite: '成员邀请',
}

export default function SmsLogsPage() {
  const [logs, setLogs] = useState<SmsLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [phoneFilter, setPhoneFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const perPage = 20

  const fetchLogs = useCallback(async (p: number, phone: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: String(p),
        per_page: String(perPage),
      })
      if (phone)
        params.set('phone', phone)
      const res = await get<SmsLogsResponse>(
        `/admin/sms-logs?${params.toString()}`,
      )
      setLogs(res.items)
      setTotal(res.total)
      setPage(res.page)
    }
    catch (e) {
      console.error(e)
    }
    finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchLogs(1, '')
  }, [fetchLogs])

  const totalPages = Math.ceil(total / perPage)

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <Input
          className="w-[200px]"
          placeholder="按手机号搜索"
          value={phoneFilter}
          onChange={e => setPhoneFilter(e.target.value)}
        />
        <Button variant="secondary" onClick={() => fetchLogs(1, phoneFilter)}>
          搜索
        </Button>
        <Button
          variant="tertiary"
          onClick={() => {
            setPhoneFilter('')
            fetchLogs(1, '')
          }}
        >
          重置
        </Button>
        <span className="ml-auto system-xs-regular text-text-tertiary">
          共
          {' '}
          {total}
          {' '}
          条记录
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-divider-subtle">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-divider-subtle bg-background-section">
              <th className="px-4 py-2 system-sm-semibold">手机号</th>
              <th className="px-4 py-2 system-sm-semibold">验证码</th>
              <th className="px-4 py-2 system-sm-semibold">用途</th>
              <th className="px-4 py-2 system-sm-semibold">发送时间</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-8 text-center text-text-tertiary"
                    >
                      加载中...
                    </td>
                  </tr>
                )
              : logs.length === 0
                ? (
                    <tr>
                      <td
                        colSpan={4}
                        className="px-4 py-8 text-center text-text-tertiary"
                      >
                        暂无数据
                      </td>
                    </tr>
                  )
                : (
                    logs.map(log => (
                      <tr
                        key={log.id}
                        className="border-b border-divider-subtle last:border-b-0"
                      >
                        <td className="px-4 py-2 system-sm-regular">{log.phone}</td>
                        <td className="px-4 py-2 font-mono system-sm-regular">
                          {log.code || '-'}
                        </td>
                        <td className="px-4 py-2 system-sm-regular">
                          {PURPOSE_LABELS[log.purpose] || log.purpose}
                        </td>
                        <td className="px-4 py-2 system-sm-regular text-text-tertiary">
                          {log.sent_at
                            ? new Date(log.sent_at).toLocaleString('zh-CN')
                            : '-'}
                        </td>
                      </tr>
                    ))
                  )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button
            variant="tertiary"
            size="small"
            disabled={page <= 1}
            onClick={() => fetchLogs(page - 1, phoneFilter)}
          >
            上一页
          </Button>
          <span className="system-sm-regular text-text-secondary">
            {page}
            {' '}
            /
            {totalPages}
          </span>
          <Button
            variant="tertiary"
            size="small"
            disabled={page >= totalPages}
            onClick={() => fetchLogs(page + 1, phoneFilter)}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}
