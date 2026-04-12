'use client'

import { RiLoader4Line, RiSave3Line } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import Button from '@/app/components/base/button'
import { toast } from '@/app/components/base/ui/toast'
import { get, put } from '@/service/base'

type RebateConfigData = {
  id: string
  rebate_rate: string
  cost_rate: string
  settlement_hour: number
  is_enabled: boolean
  updated_by: string | null
  created_at: string
  updated_at: string
}

export default function RebateConfigPage() {
  const [config, setConfig] = useState<RebateConfigData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // Form state
  const [rebateRate, setRebateRate] = useState('')
  const [costRate, setCostRate] = useState('')
  const [settlementHour, setSettlementHour] = useState(2)
  const [isEnabled, setIsEnabled] = useState(true)

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await get<RebateConfigData>('/creator/admin/rebate/config')
      setConfig(resp)
      setRebateRate(resp.rebate_rate)
      setCostRate(resp.cost_rate)
      setSettlementHour(resp.settlement_hour)
      setIsEnabled(resp.is_enabled)
    }
    catch {
      toast.error('加载返点配置失败')
    }
    finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  const handleSave = async () => {
    const rate = Number.parseFloat(rebateRate)
    const cost = Number.parseFloat(costRate)
    if (isNaN(rate) || rate < 0 || rate > 100) {
      toast.error('返点比例必须在 0-100 之间')
      return
    }
    if (isNaN(cost) || cost < 0 || cost > 100) {
      toast.error('成本比例必须在 0-100 之间')
      return
    }

    setSaving(true)
    try {
      const resp = await put<RebateConfigData>('/creator/admin/rebate/config', {
        body: {
          rebate_rate: rate,
          cost_rate: cost,
          settlement_hour: settlementHour,
          is_enabled: isEnabled,
        },
      })
      setConfig(resp)
      toast.success('返点配置已保存')
    }
    catch {
      toast.error('保存失败')
    }
    finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RiLoader4Line className="h-6 w-6 animate-spin text-text-quaternary" />
      </div>
    )
  }

  // Calculate example for preview
  const exampleConsumption = 1000
  const rateNum = Number.parseFloat(rebateRate) || 0
  const costNum = Number.parseFloat(costRate) || 0
  const exampleProfit = costNum > 0
    ? exampleConsumption * (1 - costNum / 100)
    : exampleConsumption
  const exampleRebate = exampleProfit * rateNum / 100

  return (
    <div className="space-y-8">
      {/* Enable toggle */}
      <div className="flex items-center justify-between rounded-xl border border-divider-regular bg-components-panel-bg p-4">
        <div>
          <div className="text-sm font-semibold text-text-primary">启用返点功能</div>
          <div className="mt-1 text-xs text-text-tertiary">
            开启后，空间所有者邀请的下级用户消耗产生的利润，将按设定比例返点给邀请人。
          </div>
        </div>
        <button
          type="button"
          onClick={() => setIsEnabled(v => !v)}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${isEnabled ? 'bg-components-toggle-bg' : 'bg-gray-200'}`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${isEnabled ? 'translate-x-5' : 'translate-x-0'}`}
          />
        </button>
      </div>

      {/* Rate config */}
      <div className="rounded-xl border border-divider-regular p-6">
        <div className="mb-6 text-sm font-semibold text-text-primary">返点规则配置</div>

        <div className="grid grid-cols-2 gap-6">
          {/* Rebate rate */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              返点比例 (%)
            </label>
            <input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={rebateRate}
              onChange={e => setRebateRate(e.target.value)}
              className="w-full rounded-lg border border-divider-regular bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary outline-none focus:border-components-input-border-active"
              placeholder="例如 10"
            />
            <div className="mt-1 text-xs text-text-quaternary">
              下级用户消耗利润的百分比，作为返点给上级
            </div>
          </div>

          {/* Cost rate */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              成本比例 (%)
            </label>
            <input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={costRate}
              onChange={e => setCostRate(e.target.value)}
              className="w-full rounded-lg border border-divider-regular bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary outline-none focus:border-components-input-border-active"
              placeholder="例如 0（不填成本则按消耗全额计算）"
            />
            <div className="mt-1 text-xs text-text-quaternary">
              平台成本占消耗的百分比。填 0 表示不扣成本，直接按消耗金额 × 返点比例计算。
            </div>
          </div>

          {/* Settlement hour */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              结算时间
            </label>
            <select
              value={settlementHour}
              onChange={e => setSettlementHour(Number.parseInt(e.target.value))}
              className="w-full rounded-lg border border-divider-regular bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary outline-none focus:border-components-input-border-active"
            >
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{`每日 ${String(i).padStart(2, '0')}:00`}</option>
              ))}
            </select>
            <div className="mt-1 text-xs text-text-quaternary">
              每日固定时间结算前一天的消耗返点
            </div>
          </div>
        </div>

        {/* Preview */}
        <div className="mt-6 rounded-lg bg-background-section p-4">
          <div className="mb-2 text-xs font-medium text-text-tertiary">返点计算预览</div>
          <div className="text-sm text-text-secondary">
            假设下级用户前一天消耗
            {' '}
            <span className="font-mono font-semibold">
              ¥
              {exampleConsumption.toFixed(2)}
            </span>
            {costNum > 0 && (
              <>
                ，扣除成本
                {' '}
                <span className="font-mono">
                  {costNum}
                  %
                </span>
                {' '}
                =
                {' '}
                <span className="font-mono font-semibold">
                  ¥
                  {(exampleConsumption * costNum / 100).toFixed(2)}
                </span>
                ，利润
                {' '}
                <span className="font-mono font-semibold">
                  ¥
                  {exampleProfit.toFixed(2)}
                </span>
              </>
            )}
            ，返点
            {' '}
            <span className="font-mono">
              {rateNum}
              %
            </span>
            {' '}
            =&nbsp;
            <span className="font-mono font-bold text-state-success-text">
              ¥
              {exampleRebate.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Save button */}
      <div className="flex justify-end">
        <Button variant="primary" disabled={saving} onClick={handleSave}>
          {saving
            ? <RiLoader4Line className="mr-1.5 h-4 w-4 animate-spin" />
            : <RiSave3Line className="mr-1.5 h-4 w-4" />}
          保存配置
        </Button>
      </div>

      {/* Last updated info */}
      {config && (
        <div className="text-xs text-text-quaternary">
          最后更新：
          {new Date(config.updated_at).toLocaleString('zh-CN', { hour12: false })}
        </div>
      )}
    </div>
  )
}
