'use client'

import type { ChallengeSessionInfo } from '@/types/social-publish'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import Spinner from '@/app/components/base/spinner'
import {
  abortSocialPublishChallenge,
  fetchSocialPublishChallenge,
  submitSocialPublishChallengeCode,
  triggerSocialPublishChallengeSms,
} from '@/service/social-publish'

const POLL_INTERVAL_MS = 2_000

type Props = {
  challengeSessionId: string
  /**
   * Called when sau marks the session terminal (completed / aborted).
   *  Parent should resume normal status polling — the auth flow may have
   *  resumed and is now back to scanning, or it may have failed.
   */
  onTerminal: () => void
  /**
   * Called when the user explicitly aborts the SMS verification.
   *  Parent typically closes the modal.
   */
  onAbort?: () => void
}

/**
 * SMS verification panel surfaced inside the auth modal when sau detects
 * a 短信验证 challenge. Two user actions:
 *
 *   1. "Send code" — POST trigger-sms; sau worker clicks the「获取验证码」
 *      button on the live chromium page so 抖音 sends the OTP to the
 *      user's bound phone.
 *   2. "Submit" with a 6-digit code — POST submit-code; sau worker
 *      fills the input + clicks 下一步.
 *
 * The panel polls /challenge/{id} so it can show「提交中...」after
 * dispatch and surface sau's last_action_detail (e.g. "未找到验证码输入框").
 */
export function SmsChallengePanel({
  challengeSessionId,
  onTerminal,
  onAbort,
}: Props) {
  const { t } = useTranslation('socialPublish')
  const [info, setInfo] = useState<ChallengeSessionInfo | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [smsSent, setSmsSent] = useState(false)

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const generationRef = useRef(0)

  const clearPoll = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const poll = useCallback(
    async (gen: number) => {
      if (gen !== generationRef.current)
        return
      try {
        const res = await fetchSocialPublishChallenge(challengeSessionId)
        if (gen !== generationRef.current)
          return
        setInfo(res)
        if (res.status === 'completed' || res.status === 'aborted') {
          clearPoll()
          onTerminal()
          return
        }
      }
      catch (e) {
        // 404 means TTL expired or worker already consumed; bail.
        const code = (e as { code?: string })?.code
        if (code === 'session_expired' || (e as { status?: number })?.status === 404) {
          clearPoll()
          onTerminal()
          return
        }
      }
      pollTimerRef.current = setTimeout(() => poll(gen), POLL_INTERVAL_MS)
    },
    [challengeSessionId, clearPoll, onTerminal],
  )

  useEffect(() => {
    generationRef.current += 1
    const gen = generationRef.current
    poll(gen)
    return () => {
      generationRef.current += 1
      clearPoll()
    }
  }, [poll, clearPoll])

  const handleTriggerSms = useCallback(async () => {
    setBusy(true)
    setErrorMsg(null)
    try {
      await triggerSocialPublishChallengeSms(challengeSessionId)
      setSmsSent(true)
    }
    catch (e) {
      const c = (e as { code?: string })?.code ?? 'social_publish_error'
      setErrorMsg(t(`auth.errors.${c}`, t('auth.errors.unknown')))
    }
    finally {
      setBusy(false)
    }
  }, [challengeSessionId, t])

  const handleSubmitCode = useCallback(async () => {
    const trimmed = code.trim()
    if (!/^\d{4,8}$/.test(trimmed)) {
      setErrorMsg(t('auth.smsChallenge.invalidCode'))
      return
    }
    setBusy(true)
    setErrorMsg(null)
    try {
      await submitSocialPublishChallengeCode(challengeSessionId, trimmed)
    }
    catch (e) {
      const c = (e as { code?: string })?.code ?? 'social_publish_error'
      setErrorMsg(t(`auth.errors.${c}`, t('auth.errors.unknown')))
    }
    finally {
      setBusy(false)
    }
  }, [challengeSessionId, code, t])

  const handleAbort = useCallback(async () => {
    setBusy(true)
    try {
      await abortSocialPublishChallenge(challengeSessionId)
    }
    catch {
      // best-effort; the modal will close regardless
    }
    finally {
      setBusy(false)
      onAbort?.()
    }
  }, [challengeSessionId, onAbort])

  return (
    <div className="flex w-full flex-col gap-4 p-2">
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
        {t('auth.smsChallenge.headline')}
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm text-text-secondary">
          {t('auth.smsChallenge.step1')}
        </p>
        <Button
          variant="primary"
          onClick={handleTriggerSms}
          disabled={busy}
          loading={busy && !smsSent}
        >
          {smsSent
            ? t('auth.smsChallenge.smsSent')
            : t('auth.smsChallenge.sendCode')}
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm text-text-secondary">
          {t('auth.smsChallenge.step2')}
        </label>
        <Input
          value={code}
          onChange={e =>
            setCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
          placeholder="000000"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={8}
          data-testid="sms-code-input"
        />
        <Button
          variant="primary"
          onClick={handleSubmitCode}
          disabled={busy || !code.trim()}
          loading={busy && !!code.trim()}
        >
          {t('auth.smsChallenge.submit')}
        </Button>
      </div>

      {errorMsg && (
        <p className="text-sm text-red-600">{errorMsg}</p>
      )}

      {info?.last_action_detail && (
        <p className="text-xs text-text-tertiary">
          {t('auth.smsChallenge.lastDetail', { detail: info.last_action_detail })}
        </p>
      )}

      {info?.status === 'user_submitted' && (
        <div className="flex items-center gap-2 text-xs text-text-tertiary">
          <Spinner loading className="h-3 w-3" />
          {t('auth.smsChallenge.processing')}
        </div>
      )}

      <Button variant="ghost" onClick={handleAbort} disabled={busy}>
        {t('auth.smsChallenge.giveUp')}
      </Button>
    </div>
  )
}
