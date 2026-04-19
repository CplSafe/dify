'use client'
/* eslint-disable react/set-state-in-effect -- close-reset pattern mirrors auth-qr-modal.tsx */

import type {
  BatchCreateResultItem,
  BatchCreateTaskTarget,
  CreateTaskRequest,
  SocialPublishAccount,
  SocialPublishPlatform,
  SocialPublishPlatformPayload,
  SocialPublishTask,
  SocialPublishTaskStatus,
} from '@/types/social-publish'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import Spinner from '@/app/components/base/spinner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/app/components/base/ui/dialog'
import {
  createSocialPublishTask,
  createSocialPublishTasksBatch,
  fetchSocialPublishAccounts,
  fetchSocialPublishTask,
} from '@/service/social-publish'
import { SmsChallengePanel } from './sms-challenge-panel'

const POLL_INTERVAL_MS = 3_000
const TERMINAL_STATUSES: SocialPublishTaskStatus[] = ['success', 'failed']
const TITLE_MAX = 200
const DESC_MAX = 2_000
const TAGS_MAX = 10
const LOCATION_MAX = 80
const BATCH_MAX = 10

// Account-creation set drives platform-tab visibility. Stays in sync with
// SUPPORTED_PLATFORMS_P1 on the backend (P4 = douyin + xhs; ks coming
// once upstream cookie_gen lands).
const SUPPORTED_PLATFORMS: SocialPublishPlatform[] = ['douyin', 'xhs']
// Subset of platforms whose uploader actually consumes a location field.
// Platforms outside this set hide the location input in the drawer.
const LOCATION_PLATFORMS = new Set<SocialPublishPlatform>(['douyin', 'xhs'])

type Props = {
  open: boolean
  workId: string
  /** Pre-fill the title field — typically the work's existing title. */
  defaultTitle?: string
  onOpenChange: (open: boolean) => void
  /**
   * Fired when at least one target reached `success`; lets the parent
   *  invalidate caches. Receives the first successful task — callers that
   *  need every result should poll the list endpoint.
   */
  onPublishSuccess?: (task: SocialPublishTask) => void
}

type Phase = 'form' | 'submitting' | 'tracking' | 'done' | 'partial' | 'error'

type AccountsByPlatform = Record<SocialPublishPlatform, SocialPublishAccount[]>

function emptyAccountsByPlatform(): AccountsByPlatform {
  return { douyin: [], xhs: [], ks: [] }
}

function parseTags(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map(t => t.trim())
    .filter(Boolean)
    .slice(0, TAGS_MAX)
}

function buildPlatformPayload(
  platform: SocialPublishPlatform,
  location: string,
): SocialPublishPlatformPayload | undefined {
  if (!LOCATION_PLATFORMS.has(platform))
    return undefined
  const trimmed = location.trim().slice(0, LOCATION_MAX)
  if (!trimmed)
    return undefined
  return { location: trimmed }
}

export function PublishDrawer({
  open,
  workId,
  defaultTitle,
  onOpenChange,
  onPublishSuccess,
}: Props) {
  const { t } = useTranslation('socialPublish')

  const [accountsByPlatform, setAccountsByPlatform]
    = useState<AccountsByPlatform>(emptyAccountsByPlatform)
  const [accountsLoading, setAccountsLoading] = useState(false)
  // Selected account ids — multi-select. Includes accounts from any
  // platform; per-account location lives in `locationByAccount`.
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([])
  const [locationByAccount, setLocationByAccount] = useState<
    Record<string, string>
  >({})

  const [title, setTitle] = useState(defaultTitle ?? '')
  const [tagsRaw, setTagsRaw] = useState('')
  const [desc, setDesc] = useState('')

  const [phase, setPhase] = useState<Phase>('form')
  const [task, setTask] = useState<SocialPublishTask | null>(null)
  const [errorCode, setErrorCode] = useState<string | null>(null)
  // Per-target results from the batch endpoint, surfaced in the partial /
  // done states so the user can see which accounts went through.
  const [batchResults, setBatchResults] = useState<BatchCreateResultItem[]>([])
  // P7-extra: when sau worker is mid-flow waiting for SMS verification,
  // the publish task's poll response carries challenge_session_id. We
  // swap the spinner for SmsChallengePanel so the user can complete the
  // SMS flow without having to leave the publish modal.
  const [challengeSessionId, setChallengeSessionId] = useState<string | null>(
    null,
  )

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const generationRef = useRef(0)

  const clearPoll = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const localizeError = useCallback(
    (code: string | undefined | null) => {
      if (!code)
        return t('auth.errors.unknown')
      return t(`auth.errors.${code}`, t('auth.errors.unknown'))
    },
    [t],
  )

  // ---------- accounts ----------

  // Load active accounts for every supported platform when the drawer
  // opens. The previous implementation only fetched douyin — now we need
  // every platform so the user can publish across them.
  useEffect(() => {
    if (!open)
      return
    let cancelled = false
    setAccountsLoading(true)
    Promise.all(
      SUPPORTED_PLATFORMS.map(p =>
        fetchSocialPublishAccounts(p)
          .then(res => ({ platform: p, accounts: res.data ?? [] }))
          .catch(() => ({
            platform: p,
            accounts: [] as SocialPublishAccount[],
          })),
      ),
    )
      .then((results) => {
        if (cancelled)
          return
        const next = emptyAccountsByPlatform()
        for (const { platform, accounts } of results)
          next[platform] = accounts.filter(a => a.status === 'active')
        setAccountsByPlatform(next)
        // Auto-select when there's exactly one active account across all
        // supported platforms — keeps the single-account UX from P2.
        const total = SUPPORTED_PLATFORMS.flatMap(p => next[p])
        if (total.length === 1)
          setSelectedAccountIds([total[0].id])
      })
      .finally(() => {
        if (!cancelled)
          setAccountsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const accountsFlat = useMemo(
    () =>
      SUPPORTED_PLATFORMS.flatMap(p =>
        accountsByPlatform[p].map(a => ({ platform: p, account: a })),
      ),
    [accountsByPlatform],
  )
  const accountById = useMemo(() => {
    const map = new Map<
      string,
      { platform: SocialPublishPlatform, account: SocialPublishAccount }
    >()
    for (const entry of accountsFlat) map.set(entry.account.id, entry)
    return map
  }, [accountsFlat])

  const toggleAccount = useCallback((accountId: string) => {
    setSelectedAccountIds((current) => {
      if (current.includes(accountId))
        return current.filter(id => id !== accountId)
      if (current.length >= BATCH_MAX)
        return current
      return [...current, accountId]
    })
  }, [])

  // ---------- reset ----------

  const resetRef = useRef<() => void>(() => {})
  resetRef.current = () => {
    generationRef.current += 1
    clearPoll()
    setPhase('form')
    setTask(null)
    setErrorCode(null)
    setBatchResults([])
    setChallengeSessionId(null)
    setTitle(defaultTitle ?? '')
    setTagsRaw('')
    setDesc('')
    setSelectedAccountIds([])
    setLocationByAccount({})
  }
  useEffect(() => {
    if (!open)
      resetRef.current()
    return () => clearPoll()
  }, [open, clearPoll])

  // ---------- poll ----------

  const pollOnce = useCallback(
    async (taskId: string, gen: number) => {
      if (gen !== generationRef.current)
        return
      try {
        const res = await fetchSocialPublishTask(taskId)
        if (gen !== generationRef.current)
          return
        setTask(res.task)
        // P7-extra: surface (or clear) the SMS challenge id every poll
        // tick so the modal can swap to / from SmsChallengePanel as the
        // sau worker enters / exits the awaiting_user state.
        setChallengeSessionId(res.challenge_session_id ?? null)
        if (TERMINAL_STATUSES.includes(res.task.status)) {
          clearPoll()
          if (res.task.status === 'success') {
            setPhase('done')
            onPublishSuccess?.(res.task)
          }
          else {
            setPhase('error')
            setErrorCode(
              res.result.error_code ?? res.task.error_code ?? 'upload_failed',
            )
          }
          return
        }
      }
      catch {
        // transient — keep polling
      }
      pollTimerRef.current = setTimeout(
        () => pollOnce(taskId, gen),
        POLL_INTERVAL_MS,
      )
    },
    [clearPoll, onPublishSuccess],
  )

  // ---------- submit ----------

  const submit = useCallback(async () => {
    const trimmedTitle = title.trim()
    if (!trimmedTitle) {
      setErrorCode('task_invalid_payload')
      setPhase('error')
      return
    }
    if (selectedAccountIds.length === 0)
      return
    generationRef.current += 1
    const gen = generationRef.current
    clearPoll()
    setPhase('submitting')
    setErrorCode(null)
    setBatchResults([])
    setChallengeSessionId(null)

    const tags = parseTags(tagsRaw)
    const trimmedDesc = desc.trim() || undefined

    if (selectedAccountIds.length === 1) {
      // Single-target path keeps the per-task poll behaviour from P2 so
      // the user sees real-time queued → running → success transitions.
      const accountId = selectedAccountIds[0]
      const entry = accountById.get(accountId)
      if (!entry) {
        setPhase('error')
        setErrorCode('account_not_found')
        return
      }
      const body: CreateTaskRequest = {
        account_id: accountId,
        work_id: workId,
        title: trimmedTitle,
        tags,
        desc: trimmedDesc,
        platform_payload: buildPlatformPayload(
          entry.platform,
          locationByAccount[accountId] ?? '',
        ),
      }
      try {
        const res = await createSocialPublishTask(body)
        if (gen !== generationRef.current)
          return
        setPhase('tracking')
        setTask({
          id: res.task_id,
          account_id: accountId,
          work_id: workId,
          platform: entry.platform,
          status: res.status,
          result_url: null,
          error_code: null,
          error_message: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
        pollTimerRef.current = setTimeout(
          () => pollOnce(res.task_id, gen),
          POLL_INTERVAL_MS,
        )
      }
      catch (e) {
        if (gen !== generationRef.current)
          return
        const code = (e as { code?: string })?.code ?? 'social_publish_error'
        setErrorCode(code)
        setPhase('error')
      }
      return
    }

    // Multi-target path uses the batch endpoint. Every target dispatches
    // independently server-side so a single failure doesn't block the
    // others — surfaces a per-row table after the call completes.
    const targets: BatchCreateTaskTarget[] = []
    for (const id of selectedAccountIds) {
      const entry = accountById.get(id)
      if (!entry)
        continue
      const platformPayload = buildPlatformPayload(
        entry.platform,
        locationByAccount[id] ?? '',
      )
      // Omit `platform_payload` entirely when no extras apply so the
      // request body stays minimal and matches the optional-field shape
      // the backend expects.
      targets.push(
        platformPayload
          ? { account_id: id, platform_payload: platformPayload }
          : { account_id: id },
      )
    }
    try {
      const res = await createSocialPublishTasksBatch({
        work_id: workId,
        title: trimmedTitle,
        tags,
        desc: trimmedDesc,
        targets,
      })
      if (gen !== generationRef.current)
        return
      setBatchResults(res.results)
      const allSucceeded = res.results.every(r => r.success)
      const allFailed = res.results.every(r => !r.success)
      if (allFailed) {
        setPhase('error')
        setErrorCode(res.results[0]?.error_code ?? 'social_publish_error')
        return
      }
      setPhase(allSucceeded ? 'done' : 'partial')
      // Fire onPublishSuccess with the first task that did go through so
      // the parent invalidates its cache. Per-row polling lives in the
      // task list page — keeping the drawer simple.
      const firstSuccess = res.results.find(r => r.success && r.task_id)
      if (firstSuccess) {
        const entry = accountById.get(firstSuccess.account_id)
        onPublishSuccess?.({
          id: firstSuccess.task_id!,
          account_id: firstSuccess.account_id,
          work_id: workId,
          platform: entry?.platform ?? 'douyin',
          status: 'queued',
          result_url: null,
          error_code: null,
          error_message: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
      }
    }
    catch (e) {
      if (gen !== generationRef.current)
        return
      const code = (e as { code?: string })?.code ?? 'social_publish_error'
      setErrorCode(code)
      setPhase('error')
    }
  }, [
    accountById,
    clearPoll,
    desc,
    locationByAccount,
    onPublishSuccess,
    pollOnce,
    selectedAccountIds,
    tagsRaw,
    title,
    workId,
  ])

  const submitDisabled
    = phase === 'submitting'
      || phase === 'tracking'
      || selectedAccountIds.length === 0
      || !title.trim()

  // ---------- view ----------

  const noActiveAccounts = !accountsLoading && accountsFlat.length === 0

  const accountSelector = (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-text-secondary">
        {t('publish.accounts')}
      </label>
      {accountsLoading
        ? (
            <div className="flex items-center gap-2 text-sm text-text-tertiary">
              <Spinner loading className="h-3 w-3" />
              ...
            </div>
          )
        : noActiveAccounts
          ? (
              <p className="text-sm text-amber-700">{t('publish.noActiveAccount')}</p>
            )
          : (
              <div className="flex flex-wrap gap-2">
                {accountsFlat.map(({ platform, account }) => {
                  const selected = selectedAccountIds.includes(account.id)
                  return (
                    <button
                      key={account.id}
                      type="button"
                      onClick={() => toggleAccount(account.id)}
                      aria-pressed={selected}
                      data-testid={`account-chip-${account.id}`}
                      className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-colors ${
                        selected
                          ? 'border-primary-500 bg-primary-50 text-primary-700'
                          : 'border-divider-subtle bg-components-input-bg-normal text-text-secondary hover:border-divider-deep'
                      }`}
                    >
                      <span className="font-medium">
                        {t(`platforms.${platform}`)}
                      </span>
                      <span>{account.display_name ?? account.id}</span>
                    </button>
                  )
                })}
              </div>
            )}
      {selectedAccountIds.length >= BATCH_MAX && (
        <p className="text-xs text-amber-700">
          {t('publish.batchCapHint', { max: BATCH_MAX })}
        </p>
      )}
    </div>
  )

  const perAccountLocationFields = selectedAccountIds
    .map((id) => {
      const entry = accountById.get(id)
      if (!entry || !LOCATION_PLATFORMS.has(entry.platform))
        return null
      const value = locationByAccount[id] ?? ''
      return (
        <div className="flex flex-col gap-1" key={id}>
          <label className="text-xs font-medium text-text-secondary">
            {t('publish.locationFor', {
              platform: t(`platforms.${entry.platform}`),
              name: entry.account.display_name ?? entry.account.id,
            })}
          </label>
          <Input
            value={value}
            onChange={e =>
              setLocationByAccount(prev => ({
                ...prev,
                [id]: e.target.value.slice(0, LOCATION_MAX),
              }))}
            placeholder={t('publish.locationPlaceholder')}
            maxLength={LOCATION_MAX}
            data-testid={`location-input-${id}`}
          />
        </div>
      )
    })
    .filter(Boolean)

  const formBody = (
    <div className="flex flex-col gap-4">
      {accountSelector}

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-text-secondary">
          {t('publish.videoTitle')}
        </label>
        <Input
          value={title}
          onChange={e => setTitle(e.target.value.slice(0, TITLE_MAX))}
          placeholder={t('publish.videoTitlePlaceholder')}
          maxLength={TITLE_MAX}
        />
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-text-secondary">
          {t('publish.tags')}
        </label>
        <Input
          value={tagsRaw}
          onChange={e => setTagsRaw(e.target.value)}
          placeholder={t('publish.tagsPlaceholder')}
        />
        <p className="text-xs text-text-tertiary">{t('publish.tagsHint')}</p>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-text-secondary">
          {t('publish.desc')}
        </label>
        <textarea
          value={desc}
          onChange={e => setDesc(e.target.value.slice(0, DESC_MAX))}
          placeholder={t('publish.descPlaceholder')}
          maxLength={DESC_MAX}
          rows={4}
          className="resize-none rounded-md border border-divider-subtle bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary"
        />
      </div>

      {perAccountLocationFields.length > 0 && (
        <div className="flex flex-col gap-2 rounded-md border border-divider-subtle bg-components-input-bg-normal/40 p-3">
          <p className="text-xs font-medium text-text-secondary">
            {t('publish.locationGroup')}
          </p>
          {perAccountLocationFields}
        </div>
      )}

      {phase === 'error' && errorCode && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {localizeError(errorCode)}
        </div>
      )}
    </div>
  )

  // P7-extra: when sau worker is paused waiting for SMS verification,
  // show the SMS-relay panel inline so the user can complete the
  // challenge without leaving this modal. Once the user submits or aborts,
  // the next poll tick will clear challengeSessionId and we revert to the
  // regular tracking spinner.
  const trackingChallengeBody = challengeSessionId !== null && (
    <SmsChallengePanel
      challengeSessionId={challengeSessionId}
      onTerminal={() => {
        /* poll loop will refresh task status; nothing to do here */
      }}
      onAbort={() => onOpenChange(false)}
    />
  )
  const trackingSpinnerBody = challengeSessionId === null && (
    <div className="flex flex-col items-center gap-3 py-6">
      <Spinner loading className="h-5 w-5 text-text-tertiary" />
      <p className="text-sm text-text-secondary">
        {task?.status === 'queued'
          ? t('publish.queued')
          : t(`publish.statusLabel.${task?.status ?? 'pending'}`)}
      </p>
      <p className="text-xs text-text-tertiary">{t('publish.tracking')}</p>
    </div>
  )
  const trackingBody = (
    <>
      {trackingChallengeBody}
      {trackingSpinnerBody}
    </>
  )

  const doneBody = (
    <div className="flex flex-col items-center gap-3 py-6">
      <p className="text-base font-semibold text-emerald-600">
        {t('publish.success')}
      </p>
      {task?.result_url && (
        <a
          href={task.result_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary-600 text-sm underline"
        >
          {t('publish.successOpen')}
        </a>
      )}
    </div>
  )

  const partialBody = (
    <div className="flex flex-col gap-3 py-2">
      <p className="text-sm text-amber-700">{t('publish.partial')}</p>
      <ul className="flex flex-col gap-1 text-xs">
        {batchResults.map((r) => {
          const entry = accountById.get(r.account_id)
          const label
            = entry?.account.display_name ?? entry?.account.id ?? r.account_id
          return (
            <li
              key={r.account_id}
              className={`flex items-center justify-between rounded-md border px-2 py-1.5 ${
                r.success
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-amber-200 bg-amber-50 text-amber-800'
              }`}
              data-testid={`batch-result-${r.account_id}`}
            >
              <span>{label}</span>
              <span>
                {r.success ? t('publish.success') : localizeError(r.error_code)}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[560px] max-w-[calc(100vw-2rem)]">
        <DialogTitle className="text-base font-semibold text-text-primary">
          {t('publish.title')}
        </DialogTitle>
        <DialogDescription className="mt-1 text-sm text-text-tertiary">
          {t('publish.subtitle')}
        </DialogDescription>

        <div className="mt-5">
          {phase === 'tracking' && trackingBody}
          {phase === 'done'
            && (batchResults.length > 0 ? partialBody : doneBody)}
          {phase === 'partial' && partialBody}
          {(phase === 'form' || phase === 'submitting' || phase === 'error')
            && formBody}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          {phase === 'done' || phase === 'partial'
            ? (
                <Button variant="primary" onClick={() => onOpenChange(false)}>
                  {t('accountList.deleteConfirm.cancel')}
                </Button>
              )
            : (
                <>
                  <Button
                    variant="secondary"
                    onClick={() => onOpenChange(false)}
                    disabled={phase === 'submitting'}
                  >
                    {t('publish.cancel')}
                  </Button>
                  <Button
                    variant="primary"
                    onClick={submit}
                    loading={phase === 'submitting'}
                    disabled={submitDisabled}
                  >
                    {phase === 'submitting'
                      ? t('publish.submitting')
                      : t('publish.submit')}
                  </Button>
                </>
              )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
