'use client'
/* eslint-disable react/set-state-in-effect -- close-reset pattern mirrors topup-modal.tsx; refactor to event-driven later */

import type {
  AuthSessionStatus,
  AuthStartResponse,
} from '@/types/social-publish'
import { RiRefreshLine } from '@remixicon/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import Spinner from '@/app/components/base/spinner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/app/components/base/ui/dialog'
import {
  fetchSocialPublishAuthStatus,
  startSocialPublishAuth,
} from '@/service/social-publish'

const POLL_INTERVAL_MS = 2_000
// Hard cap mirrors backend QR_VALID_SECONDS (180s) plus a small buffer; the
// poll loop also stops on session expiry from the server.
const MAX_POLL_DURATION_MS = 200_000
const SUCCESS_DISPLAY_MS = 500

type Props = {
  open: boolean
  /** When set, restart auth on an existing expired account (re-auth flow). */
  accountId: string | null
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

type Phase = 'idle' | 'starting' | 'polling' | 'success' | 'error'

function normalizeQrSrc(qr: string): string {
  // Backend may return either a raw base64 string or an already-formed
  // data URI. Always render through a data URI so the <img> behaves the same
  // regardless of which form the contract evolves towards.
  if (qr.startsWith('data:'))
    return qr
  return `data:image/png;base64,${qr}`
}

export function AuthQrModal({
  open,
  accountId,
  onOpenChange,
  onSuccess,
}: Props) {
  const { t } = useTranslation('socialPublish')
  const [phase, setPhase] = useState<Phase>('idle')
  const [serverStatus, setServerStatus]
    = useState<AuthSessionStatus>('waiting')
  const [session, setSession] = useState<AuthStartResponse | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [secondsLeft, setSecondsLeft] = useState<number>(0)

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tickTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const startedAtRef = useRef<number>(0)
  const sessionIdRef = useRef<string | null>(null)
  /**
   * Bumped on every (re)start and on close. Any in-flight async work that
   * was scheduled before the bump must be ignored — that way close/reopen
   * and rapid refresh clicks cannot resurrect stale state.
   */
  const generationRef = useRef<number>(0)

  const clearTimers = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    if (tickTimerRef.current) {
      clearInterval(tickTimerRef.current)
      tickTimerRef.current = null
    }
    if (successTimerRef.current) {
      clearTimeout(successTimerRef.current)
      successTimerRef.current = null
    }
  }, [])

  const localizeError = useCallback(
    (code: string | undefined) => {
      if (!code)
        return t('auth.errors.unknown')
      return t(`auth.errors.${code}`, t('auth.errors.unknown'))
    },
    [t],
  )

  const beginPolling = useCallback(
    async (gen: number) => {
      if (gen !== generationRef.current)
        return
      const sid = sessionIdRef.current
      if (!sid)
        return
      if (Date.now() - startedAtRef.current > MAX_POLL_DURATION_MS) {
        setServerStatus('expired')
        clearTimers()
        return
      }
      try {
        const res = await fetchSocialPublishAuthStatus(sid)
        if (gen !== generationRef.current)
          return
        setServerStatus(res.status)
        if (res.status === 'success') {
          clearTimers()
          setPhase('success')
          successTimerRef.current = setTimeout(() => {
            if (gen === generationRef.current)
              onSuccess()
          }, SUCCESS_DISPLAY_MS)
          return
        }
        if (res.status === 'expired' || res.status === 'failed') {
          clearTimers()
          return
        }
      }
      catch (e) {
        if (gen !== generationRef.current)
          return
        const code = (e as { code?: string })?.code
        // Hard-stop on these terminal codes; otherwise keep polling — transient
        // network blips shouldn't kill the modal.
        if (
          code === 'session_expired'
          || code === 'tenant_mismatch'
          || code === 'feature_disabled'
        ) {
          setErrorMsg(localizeError(code))
          setPhase('error')
          clearTimers()
          return
        }
      }
      if (gen !== generationRef.current)
        return
      pollTimerRef.current = setTimeout(
        () => beginPolling(gen),
        POLL_INTERVAL_MS,
      )
    },
    [clearTimers, localizeError, onSuccess],
  )

  const start = useCallback(async () => {
    // Cancel any prior in-flight start/poll cycle: bump the generation, drop
    // the old session, and clear timers before calling the backend.
    generationRef.current += 1
    const gen = generationRef.current
    clearTimers()
    setPhase('starting')
    setErrorMsg(null)
    setServerStatus('waiting')
    setSession(null)
    sessionIdRef.current = null
    try {
      const res = await startSocialPublishAuth({
        platform: 'douyin',
        ...(accountId ? { account_id: accountId } : {}),
      })
      if (gen !== generationRef.current)
        return
      setSession(res)
      sessionIdRef.current = res.session_id
      startedAtRef.current = Date.now()
      setSecondsLeft(res.expires_in)
      setPhase('polling')

      tickTimerRef.current = setInterval(() => {
        if (gen !== generationRef.current) {
          if (tickTimerRef.current) {
            clearInterval(tickTimerRef.current)
            tickTimerRef.current = null
          }
          return
        }
        setSecondsLeft((prev) => {
          const next = prev - 1
          if (next <= 0) {
            if (tickTimerRef.current) {
              clearInterval(tickTimerRef.current)
              tickTimerRef.current = null
            }
            return 0
          }
          return next
        })
      }, 1_000)

      pollTimerRef.current = setTimeout(
        () => beginPolling(gen),
        POLL_INTERVAL_MS,
      )
    }
    catch (e) {
      if (gen !== generationRef.current)
        return
      const code = (e as { code?: string })?.code
      setErrorMsg(localizeError(code))
      setPhase('error')
    }
  }, [accountId, beginPolling, clearTimers, localizeError])

  // Restart whenever the modal opens AND whenever the target accountId
  // changes mid-open (re-auth flow can switch the underlying row). Closing
  // bumps the generation so any pending callbacks no-op.
  //
  // We deliberately exclude `start` and `clearTimers` from the deps array
  // and access them through refs instead. Otherwise a parent re-render
  // that hands us a fresh `onSuccess` (or any callback that ripples into
  // `start`'s identity) would re-run this effect, cancel the live polling
  // timer via the cleanup, and we'd never make it past the first 2s tick.
  const startRef = useRef(start)
  const clearTimersRef = useRef(clearTimers)
  startRef.current = start
  clearTimersRef.current = clearTimers
  useEffect(() => {
    if (open) {
      startRef.current()
    }
    else {
      generationRef.current += 1
      clearTimersRef.current()
      setPhase('idle')
      setSession(null)
      setServerStatus('waiting')
      setErrorMsg(null)
      sessionIdRef.current = null
    }
    return () => {
      generationRef.current += 1
      clearTimersRef.current()
    }
  }, [open, accountId])

  const showHint = (() => {
    if (phase === 'error')
      return errorMsg ?? t('auth.errors.unknown')
    if (phase === 'starting')
      return t('auth.loadingQr')
    if (phase === 'success')
      return t('auth.successHint')
    if (serverStatus === 'expired')
      return t('auth.expiredHint')
    if (serverStatus === 'failed')
      return t('auth.failedHint')
    if (serverStatus === 'scanned')
      return t('auth.scannedHint')
    return t('auth.scanHint')
  })()

  const canRefresh
    = phase === 'error'
      || serverStatus === 'expired'
      || serverStatus === 'failed'

  // Disable the refresh button while a new start() is in flight to avoid
  // queueing concurrent starts (the generation guard already neutralises
  // their effects, but we still want to avoid doing the network work).
  const refreshDisabled = phase === 'starting'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[420px]">
        <DialogTitle className="text-base font-semibold text-text-primary">
          {t('auth.modalTitle')}
        </DialogTitle>
        <DialogDescription className="sr-only">
          {t('auth.scanHint')}
        </DialogDescription>

        <div className="mt-5 flex flex-col items-center gap-4">
          <div className="relative flex h-56 w-56 items-center justify-center rounded-xl bg-slate-50">
            {phase === 'starting' || !session
              ? (
                  <Spinner loading className="h-6 w-6 text-text-tertiary" />
                )
              : (
                  <img
                    src={normalizeQrSrc(session.qr_image_base64)}
                    alt={t('auth.qrAltText')}
                    className="h-52 w-52 object-contain"
                  />
                )}
            {phase === 'success' && (
              <div className="inset-0 absolute flex items-center justify-center rounded-xl bg-emerald-500/85 text-base font-semibold text-white">
                {t('auth.successHint')}
              </div>
            )}
          </div>

          <p className="text-center text-sm text-text-secondary">{showHint}</p>

          {phase === 'polling' && secondsLeft > 0 && (
            <p className="text-xs text-text-tertiary">
              {t('auth.secondsLeft', { seconds: secondsLeft })}
            </p>
          )}

          <div className="mt-2 flex gap-2">
            {canRefresh && (
              <Button
                variant="secondary"
                onClick={start}
                disabled={refreshDisabled}
              >
                <RiRefreshLine className="mr-1 h-4 w-4" />
                {t('auth.refresh')}
              </Button>
            )}
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {phase === 'success' ? t('auth.done') : t('auth.close')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
