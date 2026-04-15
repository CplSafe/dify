'use client'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useRouter, useSearchParams } from '@/next/navigation'
import MailForm from './components/input-mail'

// 邀请码入口暂时关闭（产品决定）：
//   - 注册页不再展示"邀请码"输入框
//   - 后端 InvitationService.bind_invitation_on_register + /email-register 的
//     invite_code 绑定逻辑保留，日后如需恢复手动输入，只需在此加回输入控件
//     并把值拼入 invite_code query param 即可。
//   - 通过分享链接 /signup?invite_code=XXX 进入的自动绑定流程仍然可用：
//     此页读取 URL 中的 invite_code 并透传给后续步骤。
const Signup = () => {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useTranslation()

  const handleInputMailSubmitted = useCallback((email: string, result: string) => {
    const params = new URLSearchParams(searchParams)
    params.set('token', encodeURIComponent(result))
    params.set('email', encodeURIComponent(email))

    // 保留 URL 中已有的 invite_code（从分享链接带入），不再从用户输入获取
    router.push(`/signup/check-code?${params.toString()}`)
  }, [router, searchParams])

  return (
    <div className="mx-auto mt-8 w-full">
      <div className="mx-auto mb-6 w-full">
        <h2 className="title-4xl-semi-bold text-text-primary">{t('signup.createAccount', { ns: 'login' })}</h2>
        <p className="body-md-regular mt-2 text-text-tertiary">{t('signup.welcome', { ns: 'login' })}</p>
      </div>

      {/* 注册福利提示 */}
      <div className="mb-6 rounded-lg border border-primary-100 bg-primary-50/60 px-4 py-3">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-600 text-[11px] font-bold text-white">
            ¥
          </span>
          <div>
            <div className="system-sm-semibold text-primary-700">
              新用户注册赠送体验额度 50 元
            </div>
            <div className="mt-0.5 system-xs-regular text-text-tertiary">
              注册成功后自动到账，可直接用于体验平台功能
            </div>
          </div>
        </div>
      </div>

      <MailForm onSuccess={handleInputMailSubmitted} />
    </div>
  )
}

export default Signup
