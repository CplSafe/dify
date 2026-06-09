'use client'

import type {
  PayoutMethod,
  PayoutPayload,
  WithdrawalRequest,
} from '@/contract/console/agent'
import * as React from 'react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/app/components/base/ui/toast'
import {
  useAgentDashboard,
  useCreateWithdrawal,
  useWithdrawalHistory,
} from '@/service/use-agent'

const MIN_WITHDRAWAL = 100

type FormState = {
  amount: string
  method: PayoutMethod
  alipayAccount: string
  alipayName: string
  wechatId: string
  wechatName: string
  bankBank: string
  bankAccount: string
  bankName: string
}

const INITIAL_FORM: FormState = {
  amount: '',
  method: 'alipay',
  alipayAccount: '',
  alipayName: '',
  wechatId: '',
  wechatName: '',
  bankBank: '',
  bankAccount: '',
  bankName: '',
}

const buildPayload = (
  form: FormState,
): PayoutPayload | Record<string, string> => {
  switch (form.method) {
    case 'alipay':
      return { account: form.alipayAccount, name: form.alipayName }
    case 'wechat':
      return { wechat_id: form.wechatId, name: form.wechatName }
    case 'bank':
      return {
        bank: form.bankBank,
        account: form.bankAccount,
        name: form.bankName,
      }
  }
}

const isPayloadValid = (form: FormState): boolean => {
  if (form.method === 'alipay')
    return !!form.alipayAccount && !!form.alipayName
  if (form.method === 'wechat')
    return !!form.wechatId && !!form.wechatName
  return !!form.bankBank && !!form.bankAccount && !!form.bankName
}

const formatDate = (iso: string | null): string => {
  if (!iso)
    return '-'
  return iso.replace('T', ' ').slice(0, 16)
}

const HistoryRow = ({ row }: { row: WithdrawalRequest }) => {
  const { t } = useTranslation()
  return (
    <tr className="border-t border-divider-subtle">
      <td className="px-4 py-3 text-text-primary">
        ¥
        {row.amount}
      </td>
      <td className="px-4 py-3 text-text-secondary">
        {t(`agent:withdrawal.method.${row.payout_method}`)}
      </td>
      <td className="px-4 py-3">
        <span
          className={
            row.status === 'paid'
              ? 'text-text-success'
              : row.status === 'rejected'
                ? 'text-state-destructive-text'
                : 'text-text-warning'
          }
        >
          {t(`agent:withdrawal.status.${row.status}`)}
        </span>
      </td>
      <td className="px-4 py-3 text-text-tertiary">
        {formatDate(row.created_at)}
      </td>
      <td className="px-4 py-3 text-text-tertiary">{row.review_note ?? '-'}</td>
    </tr>
  )
}

const AgentWithdrawalPage = () => {
  const { t } = useTranslation()
  const dashboard = useAgentDashboard(7)
  const history = useWithdrawalHistory(1, 20)
  const create = useCreateWithdrawal()
  const [form, setForm] = useState<FormState>(INITIAL_FORM)

  const withdrawable = dashboard.data?.wallet.withdrawable ?? '0'
  const withdrawableNum = Number.parseFloat(withdrawable)

  const amountNum = Number.parseFloat(form.amount || '0')
  const canSubmit = useMemo(() => {
    if (Number.isNaN(amountNum) || amountNum < MIN_WITHDRAWAL)
      return false
    if (amountNum > withdrawableNum)
      return false
    return isPayloadValid(form)
  }, [amountNum, withdrawableNum, form])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit)
      return
    create.mutate(
      {
        amount: form.amount,
        payout_method: form.method,
        payout_payload: buildPayload(form),
      },
      {
        onSuccess: () => {
          toast.success(t('agent:withdrawal.submitted'))
          setForm({ ...INITIAL_FORM, method: form.method })
        },
        onError: (err) => {
          toast.error(String(err?.message ?? 'Failed'))
        },
      },
    )
  }

  const rows = history.data?.data ?? []

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-xl font-semibold text-text-primary">
        {t('agent:withdrawal.title')}
      </h1>

      <section className="rounded-lg border border-divider-subtle bg-background-default p-6">
        <div className="mb-4">
          <span className="text-xs text-text-tertiary">
            {t('agent:withdrawal.balance.title')}
          </span>
          <div className="text-3xl font-semibold text-text-accent">
            ¥
            {withdrawable}
          </div>
          <span className="text-xs text-text-tertiary">
            {t('agent:withdrawal.minHint', { min: MIN_WITHDRAWAL })}
          </span>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary">
              {t('agent:withdrawal.amount')}
            </label>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="number"
                min={MIN_WITHDRAWAL}
                step="0.01"
                value={form.amount}
                placeholder={t('agent:withdrawal.amountPlaceholder')}
                onChange={e => setForm({ ...form, amount: e.target.value })}
                className="border-components-input-border w-48 rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm text-components-input-text-filled"
              />
              <button
                type="button"
                onClick={() => setForm({ ...form, amount: withdrawable })}
                disabled={withdrawableNum < MIN_WITHDRAWAL}
                className="rounded-md border border-components-button-secondary-border px-3 py-1.5 text-xs text-text-secondary hover:bg-state-base-hover disabled:opacity-50"
              >
                {t('agent:withdrawal.amountAll')}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary">
              {t('agent:withdrawal.method')}
            </label>
            <div className="mt-1 flex gap-3">
              {(['alipay', 'wechat', 'bank'] as const).map(m => (
                <label key={m} className="flex items-center gap-1 text-sm">
                  <input
                    type="radio"
                    checked={form.method === m}
                    onChange={() => setForm({ ...form, method: m })}
                  />
                  {t(`agent:withdrawal.method.${m}`)}
                </label>
              ))}
            </div>
          </div>

          {form.method === 'alipay' && (
            <div className="grid grid-cols-2 gap-3">
              <input
                value={form.alipayAccount}
                onChange={e =>
                  setForm({ ...form, alipayAccount: e.target.value })}
                placeholder={t('agent:withdrawal.alipay.account')}
                className="border-components-input-border rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm"
              />
              <input
                value={form.alipayName}
                onChange={e =>
                  setForm({ ...form, alipayName: e.target.value })}
                placeholder={t('agent:withdrawal.alipay.name')}
                className="border-components-input-border rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm"
              />
            </div>
          )}
          {form.method === 'wechat' && (
            <div className="grid grid-cols-2 gap-3">
              <input
                value={form.wechatId}
                onChange={e => setForm({ ...form, wechatId: e.target.value })}
                placeholder={t('agent:withdrawal.wechat.id')}
                className="border-components-input-border rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm"
              />
              <input
                value={form.wechatName}
                onChange={e =>
                  setForm({ ...form, wechatName: e.target.value })}
                placeholder={t('agent:withdrawal.wechat.name')}
                className="border-components-input-border rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm"
              />
            </div>
          )}
          {form.method === 'bank' && (
            <div className="grid grid-cols-3 gap-3">
              <input
                value={form.bankBank}
                onChange={e => setForm({ ...form, bankBank: e.target.value })}
                placeholder={t('agent:withdrawal.bank.bank')}
                className="border-components-input-border rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm"
              />
              <input
                value={form.bankAccount}
                onChange={e =>
                  setForm({ ...form, bankAccount: e.target.value })}
                placeholder={t('agent:withdrawal.bank.account')}
                className="border-components-input-border rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm"
              />
              <input
                value={form.bankName}
                onChange={e => setForm({ ...form, bankName: e.target.value })}
                placeholder={t('agent:withdrawal.bank.name')}
                className="border-components-input-border rounded-md border bg-components-input-bg-normal px-3 py-1.5 text-sm"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={!canSubmit || create.isPending}
            className="w-fit rounded-md bg-components-button-primary-bg px-4 py-2 text-sm font-medium text-components-button-primary-text shadow-xs disabled:opacity-50"
          >
            {create.isPending
              ? t('agent:withdrawal.submitting')
              : t('agent:withdrawal.submit')}
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-text-secondary">
          {t('agent:withdrawal.history.title')}
        </h2>
        {history.isLoading
          ? (
              <div className="text-sm text-text-tertiary">Loading...</div>
            )
          : rows.length === 0
            ? (
                <div className="text-sm text-text-tertiary">
                  {t('agent:withdrawal.history.empty')}
                </div>
              )
            : (
                <div className="overflow-hidden rounded-lg border border-divider-subtle bg-background-default">
                  <table className="w-full text-sm">
                    <thead className="bg-background-section">
                      <tr className="text-left text-xs font-medium text-text-tertiary">
                        <th className="px-4 py-3">
                          {t('agent:withdrawal.history.col.amount')}
                        </th>
                        <th className="px-4 py-3">
                          {t('agent:withdrawal.history.col.method')}
                        </th>
                        <th className="px-4 py-3">
                          {t('agent:withdrawal.history.col.status')}
                        </th>
                        <th className="px-4 py-3">
                          {t('agent:withdrawal.history.col.createdAt')}
                        </th>
                        <th className="px-4 py-3">
                          {t('agent:withdrawal.history.col.note')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(r => (
                        <HistoryRow key={r.id} row={r} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
      </section>
    </div>
  )
}

export default AgentWithdrawalPage
