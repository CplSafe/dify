'use client'

import * as React from 'react'
import { useTranslation } from 'react-i18next'
import { useAgentInvitees } from '@/service/use-agent'

const formatDate = (iso: string | null): string => {
  if (!iso)
    return '-'
  return iso.slice(0, 10)
}

const AgentInviteesPage = () => {
  const { t } = useTranslation()
  const { data, isLoading, error } = useAgentInvitees()

  if (isLoading) {
    return <div className="p-6 text-sm text-text-tertiary">Loading...</div>
  }

  if (error || !data) {
    return (
      <div className="text-state-destructive-text p-6 text-sm">
        {String(error?.message ?? 'Failed to load invitees')}
      </div>
    )
  }

  const rows = data.data

  return (
    <div className="flex flex-col gap-6 p-6">
      <h1 className="text-xl font-semibold text-text-primary">
        {t('agent:invitees.title')}
      </h1>

      {rows.length === 0
        ? (
            <div className="rounded-lg border border-divider-subtle bg-background-default p-12 text-center">
              <p className="text-base font-medium text-text-primary">
                {t('agent:invitees.empty.title')}
              </p>
              <p className="mt-2 text-sm text-text-tertiary">
                {t('agent:invitees.empty.hint')}
              </p>
            </div>
          )
        : (
            <div className="overflow-hidden rounded-lg border border-divider-subtle bg-background-default">
              <table className="w-full text-sm">
                <thead className="bg-background-section">
                  <tr className="text-left text-xs font-medium text-text-tertiary">
                    <th className="px-4 py-3">{t('agent:invitees.col.email')}</th>
                    <th className="px-4 py-3">{t('agent:invitees.col.boundAt')}</th>
                    <th className="px-4 py-3 text-right">
                      {t('agent:invitees.col.monthConsumption')}
                    </th>
                    <th className="px-4 py-3 text-right">
                      {t('agent:invitees.col.totalRebate')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(row => (
                    <tr
                      key={row.invitee_account_id}
                      className="border-t border-divider-subtle"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-text-primary">
                        {row.invitee_account_id.slice(0, 8)}
                        …
                      </td>
                      <td className="px-4 py-3 text-text-secondary">
                        {formatDate(row.bound_at)}
                      </td>
                      <td className="px-4 py-3 text-right text-text-primary">
                        ¥
                        {row.month_consumption}
                      </td>
                      <td className="px-4 py-3 text-right text-text-accent">
                        ¥
                        {row.total_rebate}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
    </div>
  )
}

export default AgentInviteesPage
