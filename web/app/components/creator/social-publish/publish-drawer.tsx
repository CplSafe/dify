'use client'
/* eslint-disable react/set-state-in-effect -- close-reset pattern mirrors auth-qr-modal.tsx */

import type {
  CreateTaskRequest,
  SocialPublishAccount,
  SocialPublishTask,
  SocialPublishTaskStatus,
} from '@/types/social-publish'
import { useCallback, useEffect, useRef, useState } from 'react'
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
  fetchSocialPublishAccounts,
  fetchSocialPublishTask,
} from '@/service/social-publish'

const POLL_INTERVAL_MS = 3_000
const TERMINAL_STATUSES: SocialPublishTaskStatus[] = ['success', 'failed']
const TITLE_MAX = 200
const DESC_MAX = 2_000
const TAGS_MAX = 10

type Props = {
  open: boolean
  workId: string
  /** Pre-fill the title field — typically the work's existing title. */
  defaultTitle?: string
  onOpenChange: (open: boolean) => void
  /** Fired when a task reaches `success`; lets the parent invalidate caches. */
  onPublishSuccess?: (task: SocialPublishTask) => void
}

type Phase = 'form' | 'submitting' | 'tracking' | 'done' | 'error'

function parseTags(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map(t => t.trim())
    .filter(Boolean)
    .slice(0, TAGS_MAX)
}

export function PublishDrawer({
  open,
  workId,
  defaultTitle,
  onOpenChange,
  onPublishSuccess,
}: Props) {
  const { t } = useTranslation('socialPublish')

  const [accounts, setAccounts] = useState<SocialPublishAccount[]>([])
  const [accountsLoading, setAccountsLoading] = useState(false)
  const [accountId, setAccountId] = useState<string>('')
  const [title, setTitle] = useState(defaultTitle ?? '')
  const [tagsRaw, setTagsRaw] = useState('')
  const [desc, setDesc] = useState('')

  const [phase, setPhase] = useState<Phase>('form')
  const [task, setTask] = useState<SocialPublishTask | null>(null)
  const [errorCode, setErrorCode] = useState<string | null>(null)

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

  // Load active accounts when the drawer opens.
  useEffect(() => {
    if (!open)
      return
    let cancelled = false
    setAccountsLoading(true)
    fetchSocialPublishAccounts('douyin')
      .then((res) => {
        if (cancelled)
          return
        const active = (res.data ?? []).filter(a => a.status === 'active')
        setAccounts(active)
        if (active.length === 1)
          setAccountId(active[0].id)
      })
      .catch(() => {
        if (cancelled)
          return
        setAccounts([])
      })
      .finally(() => {
        if (!cancelled)
          setAccountsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  // Reset form / poller on close.
  const resetRef = useRef<() => void>(() => {})
  resetRef.current = () => {
    generationRef.current += 1
    clearPoll()
    setPhase('form')
    setTask(null)
    setErrorCode(null)
    setTitle(defaultTitle ?? '')
    setTagsRaw('')
    setDesc('')
    setAccountId('')
  }
  useEffect(() => {
    if (!open)
      resetRef.current()
    return () => clearPoll()
  }, [open, clearPoll])

  const pollOnce = useCallback(
    async (taskId: string, gen: number) => {
      if (gen !== generationRef.current)
        return
      try {
        const res = await fetchSocialPublishTask(taskId)
        if (gen !== generationRef.current)
          return
        setTask(res.task)
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

  const submit = useCallback(async () => {
    const trimmedTitle = title.trim()
    if (!trimmedTitle) {
      setErrorCode('task_invalid_payload')
      setPhase('error')
      return
    }
    generationRef.current += 1
    const gen = generationRef.current
    clearPoll()
    setPhase('submitting')
    setErrorCode(null)

    const body: CreateTaskRequest = {
      account_id: accountId,
      work_id: workId,
      title: trimmedTitle,
      tags: parseTags(tagsRaw),
      desc: desc.trim() || undefined,
    }
    try {
      const res = await createSocialPublishTask(body)
      if (gen !== generationRef.current)
        return
      setPhase('tracking')
      // Synthesise a minimal task row until the first poll lands.
      setTask({
        id: res.task_id,
        account_id: accountId,
        work_id: workId,
        platform: 'douyin',
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
  }, [accountId, clearPoll, desc, pollOnce, tagsRaw, title, workId])

  const submitDisabled
    = phase === 'submitting'
      || phase === 'tracking'
      || !accountId
      || !title.trim()

  const formBody = (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-text-secondary">
          {t('publish.account')}
        </label>
        {accountsLoading
          ? (
              <div className="flex items-center gap-2 text-sm text-text-tertiary">
                <Spinner loading className="h-3 w-3" />
                ...
              </div>
            )
          : accounts.length === 0
            ? (
                <p className="text-sm text-amber-700">
                  {t('publish.noActiveAccount')}
                </p>
              )
            : (
                <select
                  value={accountId}
                  onChange={e => setAccountId(e.target.value)}
                  className="rounded-md border border-divider-subtle bg-components-input-bg-normal px-3 py-2 text-sm text-text-primary"
                >
                  <option value="">{t('publish.accountPlaceholder')}</option>
                  {accounts.map(a => (
                    <option key={a.id} value={a.id}>
                      {a.display_name ?? a.id}
                    </option>
                  ))}
                </select>
              )}
      </div>

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

      {phase === 'error' && errorCode && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {localizeError(errorCode)}
        </div>
      )}
    </div>
  )

  const trackingBody = (
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[520px] max-w-[calc(100vw-2rem)]">
        <DialogTitle className="text-base font-semibold text-text-primary">
          {t('publish.title')}
        </DialogTitle>
        <DialogDescription className="mt-1 text-sm text-text-tertiary">
          {t('publish.subtitle')}
        </DialogDescription>

        <div className="mt-5">
          {phase === 'tracking' && trackingBody}
          {phase === 'done' && doneBody}
          {(phase === 'form' || phase === 'submitting' || phase === 'error')
            && formBody}
        </div>

        <div className="mt-6 flex justify-end gap-2">
          {phase === 'done'
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
