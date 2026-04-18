'use client'

import type {
  SocialPublishAccount,
  SocialPublishAccountStatus,
  SocialPublishPlatform,
} from '@/types/social-publish'
import {
  RiAddLine,
  RiDeleteBinLine,
  RiQrScan2Line,
  RiUserLine,
} from '@remixicon/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import Spinner from '@/app/components/base/spinner'
import { toast } from '@/app/components/base/ui/toast'
import {
  deleteSocialPublishAccount,
  fetchSocialPublishAccounts,
} from '@/service/social-publish'
import { cn } from '@/utils/classnames'
import { AuthQrModal } from './auth-qr-modal'
import { DeleteAccountConfirm } from './delete-account-confirm'

const STATUS_TONE: Record<SocialPublishAccountStatus, string> = {
  active: 'bg-emerald-50 text-emerald-700',
  expired: 'bg-amber-50 text-amber-700',
  pending_auth: 'bg-slate-100 text-slate-600',
}

type AuthIntent = { mode: 'create' } | { mode: 'reauth', accountId: string }

export function SocialPublishAccountList() {
  const { t } = useTranslation('socialPublish')
  const [accounts, setAccounts] = useState<SocialPublishAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [errorCode, setErrorCode] = useState<string | null>(null)
  const [authIntent, setAuthIntent] = useState<AuthIntent | null>(null)
  const [pendingDelete, setPendingDelete]
    = useState<SocialPublishAccount | null>(null)
  const [deleting, setDeleting] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    setErrorCode(null)
    try {
      const res = await fetchSocialPublishAccounts()
      setAccounts(res.data)
    }
    catch (e) {
      const code = (e as { code?: string })?.code ?? 'unknown'
      setErrorCode(code)
    }
    finally {
      setLoading(false)
    }
  }, [])

  // feature_disabled is a configuration state, not a runtime error — render
  // a dedicated empty-state below rather than a generic error banner.
  const featureDisabled = errorCode === 'feature_disabled'
  const errorMessage = errorCode
    ? t(`auth.errors.${errorCode}`, t('auth.errors.unknown'))
    : null

  useEffect(() => {
    reload()
  }, [reload])

  const handleDelete = useCallback(async () => {
    if (!pendingDelete)
      return
    setDeleting(true)
    try {
      await deleteSocialPublishAccount(pendingDelete.id)
      toast.success(t('accountList.deleteConfirm.success'))
      setPendingDelete(null)
      await reload()
    }
    catch (e) {
      const code = (e as { code?: string })?.code ?? 'unknown'
      const localized = t(
        `auth.errors.${code}`,
        t('accountList.deleteConfirm.error'),
      )
      toast.error(localized)
    }
    finally {
      setDeleting(false)
    }
  }, [pendingDelete, reload, t])

  const onAuthSuccess = useCallback(async () => {
    setAuthIntent(null)
    await reload()
  }, [reload])

  const platformLabel = useMemo(
    () => (p: SocialPublishPlatform) => t(`accountList.platform.${p}`),
    [t],
  )

  return (
    <section className="mx-auto w-full max-w-5xl px-6 py-8">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">
            {t('accountList.title')}
          </h1>
          <p className="mt-1 text-sm text-text-tertiary">
            {t('accountList.subtitle')}
          </p>
        </div>
        {!featureDisabled && (
          <Button
            variant="primary"
            onClick={() => setAuthIntent({ mode: 'create' })}
          >
            <RiAddLine className="mr-1 h-4 w-4" />
            {t('accountList.addDouyinAccount')}
          </Button>
        )}
      </header>

      {loading
        ? (
            <div className="flex items-center justify-center rounded-xl border border-divider-subtle bg-components-panel-bg py-16">
              <Spinner loading className="h-5 w-5 text-text-tertiary" />
            </div>
          )
        : featureDisabled
          ? (
              <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-divider-subtle bg-components-panel-bg py-16">
                <h3 className="text-base font-medium text-text-secondary">
                  {t('auth.errors.feature_disabled')}
                </h3>
              </div>
            )
          : errorMessage
            ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                  {errorMessage}
                </div>
              )
            : accounts.length === 0
              ? (
                  <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-divider-subtle bg-components-panel-bg py-16">
                    <RiUserLine className="h-7 w-7 text-text-quaternary" />
                    <h3 className="text-base font-medium text-text-secondary">
                      {t('accountList.empty.title')}
                    </h3>
                    <p className="max-w-md text-center text-sm text-text-tertiary">
                      {t('accountList.empty.description')}
                    </p>
                  </div>
                )
              : (
                  <ul className="space-y-2">
                    {accounts.map(acc => (
                      <li
                        key={acc.id}
                        className="flex items-center gap-4 rounded-xl border border-divider-subtle bg-components-panel-bg px-4 py-3"
                      >
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-100">
                          {acc.avatar_url
                            ? (
                                <img
                                  src={acc.avatar_url}
                                  alt={acc.display_name ?? ''}
                                  className="h-full w-full object-cover"
                                />
                              )
                            : (
                                <RiUserLine className="h-5 w-5 text-slate-400" />
                              )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-text-primary">
                            {acc.display_name ?? '—'}
                          </div>
                          <div className="mt-0.5 text-xs text-text-tertiary">
                            {platformLabel(acc.platform)}
                            {' · '}
                            {acc.last_check_at
                              ? new Date(acc.last_check_at).toLocaleString()
                              : '—'}
                          </div>
                        </div>
                        <span
                          className={cn(
                            'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium',
                            STATUS_TONE[acc.status],
                          )}
                        >
                          {t(`accountList.status.${acc.status}`)}
                        </span>
                        {acc.status === 'expired' && (
                          <Button
                            variant="secondary"
                            size="small"
                            onClick={() =>
                              setAuthIntent({ mode: 'reauth', accountId: acc.id })}
                          >
                            <RiQrScan2Line className="mr-1 h-3.5 w-3.5" />
                            {t('accountList.actions.reauth')}
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="small"
                          destructive
                          onClick={() => setPendingDelete(acc)}
                        >
                          <RiDeleteBinLine className="h-4 w-4" />
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}

      <AuthQrModal
        open={authIntent !== null}
        accountId={authIntent?.mode === 'reauth' ? authIntent.accountId : null}
        onOpenChange={(open) => {
          if (!open)
            setAuthIntent(null)
        }}
        onSuccess={onAuthSuccess}
      />

      <DeleteAccountConfirm
        open={pendingDelete !== null}
        account={pendingDelete}
        loading={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={handleDelete}
      />
    </section>
  )
}
