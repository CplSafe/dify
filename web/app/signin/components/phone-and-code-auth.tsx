'use client'

import type { FormEvent } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Button from '@/app/components/base/button'
import Input from '@/app/components/base/input'
import { toast } from '@/app/components/base/ui/toast'
import { resolvePostLoginRedirect } from '@/app/signin/utils/post-login-redirect'
import { resolveHomeRoute } from '@/app/signin/utils/resolve-home-route'
import { useRouter, useSearchParams } from '@/next/navigation'
import { sendSmsLoginCode, smsLoginVerify } from '@/service/common'

const COUNTDOWN_SECONDS = 60

export default function PhoneAndCodeAuth() {
  const { t } = useTranslation()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [countdown, setCountdown] = useState(0)

  useEffect(() => {
    if (countdown <= 0)
      return
    const timer = setTimeout(() => setCountdown(prev => prev - 1), 1000)
    return () => clearTimeout(timer)
  }, [countdown])

  const handleSendCode = useCallback(async () => {
    if (!phone || phone.length !== 11) {
      toast.error(t('sms.phoneInvalid', { ns: 'login' }))
      return
    }
    setSending(true)
    try {
      const res = await sendSmsLoginCode(phone)
      if (res.result === 'success') {
        setCodeSent(true)
        setCountdown(COUNTDOWN_SECONDS)
        toast.success(t('sms.codeSent', { ns: 'login' }))
      }
    }
    catch (error) {
      console.error(error)
    }
    finally {
      setSending(false)
    }
  }, [phone, t])

  const handleVerify = useCallback(async () => {
    if (!code) {
      toast.error(t('sms.codeEmpty', { ns: 'login' }))
      return
    }
    setVerifying(true)
    try {
      const rawInviteToken = searchParams.get('invite_token')
      const inviteToken = rawInviteToken
        ? decodeURIComponent(rawInviteToken)
        : undefined
      const res = await smsLoginVerify({
        phone,
        code,
        ...(inviteToken ? { invite_token: inviteToken } : {}),
      })
      if (res.result === 'success') {
        toast.success(t('sms.loginSuccess', { ns: 'login' }))
        router.replace(
          resolvePostLoginRedirect() || (await resolveHomeRoute()),
        )
      }
    }
    catch (error) {
      console.error(error)
    }
    finally {
      setVerifying(false)
    }
  }, [phone, code, searchParams, router, t])

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!codeSent)
      handleSendCode()
    else handleVerify()
  }

  return (
    <form onSubmit={handleSubmit}>
      {/* 注册福利提示 */}
      <div className="mb-4 rounded-lg border border-primary-100 bg-primary-50/60 px-4 py-3">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-600 text-[11px] font-bold text-white">
            ¥
          </span>
          <div>
            <div className="system-sm-semibold text-primary-700">
              {t('sms.signupBonusTitle', { ns: 'login' })}
            </div>
            <div className="mt-0.5 system-xs-regular text-text-tertiary">
              {t('sms.signupBonusDesc', { ns: 'login' })}
            </div>
          </div>
        </div>
      </div>
      <div className="mb-2">
        <label
          htmlFor="phone"
          className="my-2 system-md-semibold text-text-secondary"
        >
          {t('sms.phone', { ns: 'login' })}
        </label>
        <div className="mt-1">
          <Input
            id="phone"
            type="tel"
            maxLength={11}
            value={phone}
            placeholder={t('sms.phonePlaceholder', { ns: 'login' }) || ''}
            onChange={e => setPhone(e.target.value.replace(/\D/g, ''))}
          />
        </div>
      </div>
      {codeSent && (
        <div className="mb-2">
          <label
            htmlFor="sms-code"
            className="my-2 system-md-semibold text-text-secondary"
          >
            {t('sms.code', { ns: 'login' })}
          </label>
          <div className="mt-1 flex gap-2">
            <Input
              id="sms-code"
              type="text"
              maxLength={6}
              value={code}
              placeholder={t('sms.codePlaceholder', { ns: 'login' }) || ''}
              onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
              className="flex-1"
            />
            <Button
              type="button"
              variant="secondary"
              disabled={countdown > 0 || sending}
              onClick={handleSendCode}
              className="shrink-0"
            >
              {countdown > 0
                ? `${countdown}s`
                : t('sms.resend', { ns: 'login' })}
            </Button>
          </div>
        </div>
      )}
      <div className="mt-3">
        <Button
          type="submit"
          variant="primary"
          className="w-full"
          loading={sending || verifying}
          disabled={sending || verifying || !phone}
        >
          {codeSent
            ? t('sms.login', { ns: 'login' })
            : t('sms.sendCode', { ns: 'login' })}
        </Button>
      </div>
      <p className="mt-3 text-center system-xs-regular text-text-tertiary">
        {t('sms.autoRegisterTip', { ns: 'login' })}
      </p>
    </form>
  )
}
