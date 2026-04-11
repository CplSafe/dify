'use client'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Input from '@/app/components/base/input'
import { useRouter, useSearchParams } from '@/next/navigation'
import MailForm from './components/input-mail'

const Signup = () => {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useTranslation()

  // invite_code from URL takes priority, user can also type one manually
  const urlInviteCode = searchParams.get('invite_code') || ''
  const [inviteCodeInput, setInviteCodeInput] = useState(decodeURIComponent(urlInviteCode))

  const handleInputMailSubmitted = useCallback((email: string, result: string) => {
    const params = new URLSearchParams(searchParams)
    params.set('token', encodeURIComponent(result))
    params.set('email', encodeURIComponent(email))

    // Carry invite_code through the signup flow
    const code = inviteCodeInput.trim()
    if (code)
      params.set('invite_code', encodeURIComponent(code))
    else
      params.delete('invite_code')

    router.push(`/signup/check-code?${params.toString()}`)
  }, [router, searchParams, inviteCodeInput])

  return (
    <div className="mx-auto mt-8 w-full">
      <div className="mx-auto mb-10 w-full">
        <h2 className="title-4xl-semi-bold text-text-primary">{t('signup.createAccount', { ns: 'login' })}</h2>
        <p className="body-md-regular mt-2 text-text-tertiary">{t('signup.welcome', { ns: 'login' })}</p>
      </div>

      {/* Invite code input */}
      <div className="mb-4">
        <label htmlFor="invite_code" className="system-md-semibold my-2 text-text-secondary">
          邀请码（选填）
        </label>
        <div className="mt-1">
          <Input
            id="invite_code"
            value={inviteCodeInput}
            onChange={e => setInviteCodeInput(e.target.value)}
            placeholder="请输入邀请码，没有可留空"
            tabIndex={0}
          />
        </div>
        {inviteCodeInput.trim() && (
          <p className="mt-1 text-text-tertiary system-xs-regular">
            注册成功后将自动绑定邀请关系
          </p>
        )}
      </div>

      <MailForm onSuccess={handleInputMailSubmitted} />
    </div>
  )
}

export default Signup
