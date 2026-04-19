import * as React from 'react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/app/components/base/ui/toast'
import { useGlobalPublicStore } from '@/context/global-public-context'
import Link from '@/next/link'
import { useRouter, useSearchParams } from '@/next/navigation'
import { invitationCheck } from '@/service/common'
import { useIsLogin } from '@/service/use-common'
import { LicenseStatus } from '@/types/feature'
import { cn } from '@/utils/classnames'
import Loading from '../components/base/loading'
import MailAndCodeAuth from './components/mail-and-code-auth'
import MailAndPasswordAuth from './components/mail-and-password-auth'
import PhoneAndCodeAuth from './components/phone-and-code-auth'
import SocialAuth from './components/social-auth'
import SSOAuth from './components/sso-auth'
import Split from './split'
import { resolvePostLoginRedirect } from './utils/post-login-redirect'
import { resolveHomeRoute } from './utils/resolve-home-route'

const NormalForm = () => {
  const { t } = useTranslation()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { isLoading: isCheckLoading, data: loginData } = useIsLogin()
  const isLoggedIn = loginData?.logged_in
  const message = decodeURIComponent(searchParams.get('message') || '')
  const invite_token = decodeURIComponent(
    searchParams.get('invite_token') || '',
  )
  const [isInitCheckLoading, setIsInitCheckLoading] = useState(true)
  const [isRedirecting, setIsRedirecting] = useState(false)
  const isLoading = isCheckLoading || isInitCheckLoading || isRedirecting
  const { systemFeatures } = useGlobalPublicStore()
  const [authType, setAuthType] = useState<'code' | 'password' | 'sms'>(
    'password',
  )
  const [showORLine, setShowORLine] = useState(false)
  const [allMethodsAreDisabled, setAllMethodsAreDisabled] = useState(false)
  const [workspaceName, setWorkspaceName] = useState('')

  const isInviteLink = Boolean(invite_token && invite_token !== 'null')
  const signupHref = React.useMemo(() => {
    const inviteCode = searchParams.get('invite_code')
    return inviteCode
      ? `/signup?invite_code=${encodeURIComponent(inviteCode)}`
      : '/signup'
  }, [searchParams])

  const init = useCallback(async () => {
    try {
      if (isLoggedIn) {
        setIsRedirecting(true)
        const redirectUrl
          = resolvePostLoginRedirect() || (await resolveHomeRoute())
        router.replace(redirectUrl)
        return
      }

      if (message) {
        toast.error(message)
      }
      setAllMethodsAreDisabled(
        !systemFeatures.enable_social_oauth_login
        && !systemFeatures.enable_email_code_login
        && !systemFeatures.enable_email_password_login
        && !systemFeatures.enable_sms_code_login
        && !systemFeatures.sso_enforced_for_signin,
      )
      setShowORLine(
        (systemFeatures.enable_social_oauth_login
          || systemFeatures.sso_enforced_for_signin)
        && (systemFeatures.enable_email_code_login
          || systemFeatures.enable_email_password_login
          || systemFeatures.enable_sms_code_login),
      )
      if (systemFeatures.enable_sms_code_login)
        setAuthType('sms')
      else if (systemFeatures.enable_email_password_login)
        setAuthType('password')
      else setAuthType('code')
      if (isInviteLink) {
        const checkRes = await invitationCheck({
          url: '/activate/check',
          params: {
            token: invite_token,
          },
        })
        setWorkspaceName(checkRes?.data?.workspace_name || '')
      }
    }
    catch (error) {
      console.error(error)
      setAllMethodsAreDisabled(true)
    }
    finally {
      setIsInitCheckLoading(false)
    }
  }, [isLoggedIn, message, router, invite_token, isInviteLink, systemFeatures])
  useEffect(() => {
    init()
  }, [init])
  if (isLoading) {
    return (
      <div
        className={cn(
          'flex w-full grow flex-col items-center justify-center',
          'px-6',
          'md:px-[108px]',
        )}
      >
        <Loading type="area" />
      </div>
    )
  }
  if (systemFeatures.license?.status === LicenseStatus.LOST) {
    return (
      <div className="mx-auto mt-8 w-full">
        <div className="relative">
          <div className="rounded-lg bg-linear-to-r from-workflow-workflow-progress-bg-1 to-workflow-workflow-progress-bg-2 p-4">
            <div className="relative mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-components-card-bg shadow-lg">
              <i className="i-ri-contract-line h-5 w-5" />
              <i className="i-ri-error-warning-fill absolute -right-1 -top-1 h-4 w-4 text-text-warning-secondary" />
            </div>
            <p className="text-text-primary system-sm-medium">
              {t('licenseLost', { ns: 'login' })}
            </p>
            <p className="mt-1 text-text-tertiary system-xs-regular">
              {t('licenseLostTip', { ns: 'login' })}
            </p>
          </div>
        </div>
      </div>
    )
  }
  if (systemFeatures.license?.status === LicenseStatus.EXPIRED) {
    return (
      <div className="mx-auto mt-8 w-full">
        <div className="relative">
          <div className="rounded-lg bg-linear-to-r from-workflow-workflow-progress-bg-1 to-workflow-workflow-progress-bg-2 p-4">
            <div className="relative mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-components-card-bg shadow-lg">
              <i className="i-ri-contract-line h-5 w-5" />
              <i className="i-ri-error-warning-fill absolute -right-1 -top-1 h-4 w-4 text-text-warning-secondary" />
            </div>
            <p className="text-text-primary system-sm-medium">
              {t('licenseExpired', { ns: 'login' })}
            </p>
            <p className="mt-1 text-text-tertiary system-xs-regular">
              {t('licenseExpiredTip', { ns: 'login' })}
            </p>
          </div>
        </div>
      </div>
    )
  }
  if (systemFeatures.license?.status === LicenseStatus.INACTIVE) {
    return (
      <div className="mx-auto mt-8 w-full">
        <div className="relative">
          <div className="rounded-lg bg-linear-to-r from-workflow-workflow-progress-bg-1 to-workflow-workflow-progress-bg-2 p-4">
            <div className="relative mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-components-card-bg shadow-lg">
              <i className="i-ri-contract-line h-5 w-5" />
              <i className="i-ri-error-warning-fill absolute -right-1 -top-1 h-4 w-4 text-text-warning-secondary" />
            </div>
            <p className="text-text-primary system-sm-medium">
              {t('licenseInactive', { ns: 'login' })}
            </p>
            <p className="mt-1 text-text-tertiary system-xs-regular">
              {t('licenseInactiveTip', { ns: 'login' })}
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="mx-auto mt-8 w-full">
        {isInviteLink
          ? (
              <div className="mx-auto w-full">
                <h2 className="text-text-primary title-4xl-semi-bold">
                  {t('join', { ns: 'login' })}
                  {workspaceName}
                </h2>
                {!systemFeatures.branding.enabled && (
                  <p className="mt-2 text-text-tertiary body-md-regular">
                    {t('joinTipStart', { ns: 'login' })}
                    {workspaceName}
                    {t('joinTipEnd', { ns: 'login' })}
                  </p>
                )}
              </div>
            )
          : (
              <div className="mx-auto w-full">
                <h2 className="text-text-primary title-4xl-semi-bold">
                  {systemFeatures.branding.enabled
                    ? t('pageTitleForE', { ns: 'login' })
                    : t('pageTitle', { ns: 'login' })}
                </h2>
                <p className="mt-2 text-text-tertiary body-md-regular">
                  {t('welcome', { ns: 'login' })}
                </p>
              </div>
            )}
        <div className="relative">
          <div className="mt-6 flex flex-col gap-3">
            {systemFeatures.enable_social_oauth_login && <SocialAuth />}
            {systemFeatures.sso_enforced_for_signin && (
              <div className="w-full">
                <SSOAuth
                  protocol={systemFeatures.sso_enforced_for_signin_protocol}
                />
              </div>
            )}
          </div>

          {showORLine && (
            <div className="relative mt-6">
              <div className="flex items-center">
                <div className="h-px flex-1 bg-linear-to-r from-background-gradient-mask-transparent to-divider-regular"></div>
                <span className="px-3 text-text-tertiary system-xs-medium-uppercase">
                  {t('or', { ns: 'login' })}
                </span>
                <div className="h-px flex-1 bg-linear-to-l from-background-gradient-mask-transparent to-divider-regular"></div>
              </div>
            </div>
          )}
          {systemFeatures.enable_sms_code_login && authType === 'sms' && (
            <>
              <PhoneAndCodeAuth />
              {(systemFeatures.enable_email_code_login
                || systemFeatures.enable_email_password_login) && (
                <div
                  className="cursor-pointer py-1 text-center"
                  onClick={() => {
                    setAuthType(
                      systemFeatures.enable_email_code_login
                        ? 'code'
                        : 'password',
                    )
                  }}
                >
                  <span className="text-components-button-secondary-accent-text system-xs-medium">
                    {t('useEmail', { ns: 'login' })}
                  </span>
                </div>
              )}
              <Split className="mb-5 mt-4" />
            </>
          )}
          {(systemFeatures.enable_email_code_login
            || systemFeatures.enable_email_password_login)
          && authType !== 'sms' && (
            <>
              {systemFeatures.enable_email_code_login
                && authType === 'code' && (
                <>
                  <MailAndCodeAuth isInvite={isInviteLink} />
                  {systemFeatures.enable_email_password_login && (
                    <div
                      className="cursor-pointer py-1 text-center"
                      onClick={() => {
                        setAuthType('password')
                      }}
                    >
                      <span className="text-components-button-secondary-accent-text system-xs-medium">
                        {t('usePassword', { ns: 'login' })}
                      </span>
                    </div>
                  )}
                </>
              )}
              {systemFeatures.enable_email_password_login
                && authType === 'password' && (
                <>
                  <MailAndPasswordAuth
                    isInvite={isInviteLink}
                    isEmailSetup={systemFeatures.is_email_setup}
                    allowRegistration={systemFeatures.is_allow_register}
                  />
                  {systemFeatures.enable_email_code_login && (
                    <div
                      className="cursor-pointer py-1 text-center"
                      onClick={() => {
                        setAuthType('code')
                      }}
                    >
                      <span className="text-components-button-secondary-accent-text system-xs-medium">
                        {t('useVerificationCode', { ns: 'login' })}
                      </span>
                    </div>
                  )}
                </>
              )}
              {systemFeatures.enable_sms_code_login && (
                <div
                  className="cursor-pointer py-1 text-center"
                  onClick={() => {
                    setAuthType('sms')
                  }}
                >
                  <span className="text-components-button-secondary-accent-text system-xs-medium">
                    {t('sms.usePhone', { ns: 'login' })}
                  </span>
                </div>
              )}
              <Split className="mb-5 mt-4" />
            </>
          )}

          {systemFeatures.is_allow_register && authType === 'password' && (
            <div className="mb-3 text-[13px] font-medium leading-4 text-text-secondary">
              <span>{t('signup.noAccount', { ns: 'login' })}</span>
              <Link className="text-text-accent" href={signupHref}>
                {t('signup.signUp', { ns: 'login' })}
              </Link>
            </div>
          )}
          {allMethodsAreDisabled && (
            <>
              <div className="rounded-lg bg-linear-to-r from-workflow-workflow-progress-bg-1 to-workflow-workflow-progress-bg-2 p-4">
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-components-card-bg shadow-lg">
                  <i className="i-ri-door-lock-line h-5 w-5" />
                </div>
                <p className="text-text-primary system-sm-medium">
                  {t('noLoginMethod', { ns: 'login' })}
                </p>
                <p className="mt-1 text-text-tertiary system-xs-regular">
                  {t('noLoginMethodTip', { ns: 'login' })}
                </p>
              </div>
              <div className="relative my-2 py-2">
                <div
                  className="absolute inset-0 flex items-center"
                  aria-hidden="true"
                >
                  <div className="h-px w-full bg-linear-to-r from-background-gradient-mask-transparent via-divider-regular to-background-gradient-mask-transparent"></div>
                </div>
              </div>
            </>
          )}
          {/* {!systemFeatures.branding.enabled && (
            <>
              <div className="mt-2 block w-full text-text-tertiary system-xs-regular">
                {t('tosDesc', { ns: 'login' })}
              &nbsp;
                <Link
                  className="text-text-secondary system-xs-medium hover:underline"
                  target="_blank"
                  rel="noopener noreferrer"
                  href="https://dify.ai/terms"
                >
                  {t('tos', { ns: 'login' })}
                </Link>
              &nbsp;&&nbsp;
                <Link
                  className="text-text-secondary system-xs-medium hover:underline"
                  target="_blank"
                  rel="noopener noreferrer"
                  href="https://dify.ai/privacy"
                >
                  {t('pp', { ns: 'login' })}
                </Link>
              </div>
              {IS_CE_EDITION && (
                <div className="w-hull mt-2 block text-text-tertiary system-xs-regular">
                  {t('goToInit', { ns: 'login' })}
              &nbsp;
                  <Link
                    className="text-text-secondary system-xs-medium hover:underline"
                    href="/install"
                  >
                    {t('setAdminAccount', { ns: 'login' })}
                  </Link>
                </div>
              )}
            </>
          )} */}
        </div>
      </div>
    </>
  )
}

export default NormalForm
