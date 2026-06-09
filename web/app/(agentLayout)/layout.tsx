'use client'

import type { ReactNode } from 'react'
import * as React from 'react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/app/components/base/ui/toast'
import { usePathname, useRouter } from '@/next/navigation'
import { useUserProfile } from '@/service/use-common'

type AgentLayoutProps = {
  children: ReactNode
}

const NAV_ITEMS: ReadonlyArray<{ href: string, key: string }> = [
  { href: '/agent/dashboard', key: 'nav.dashboard' },
  { href: '/agent/invitees', key: 'nav.invitees' },
  { href: '/agent/invitation', key: 'nav.invitation' },
  { href: '/agent/withdrawal', key: 'nav.withdrawal' },
]

const AgentLayout = ({ children }: AgentLayoutProps) => {
  const router = useRouter()
  const pathname = usePathname()
  const { t } = useTranslation()
  const { data: profileData, isLoading } = useUserProfile()

  const profile = profileData?.profile
  const isAgent = profile?.is_agent === true
  const status = profile?.agent_status ?? null

  useEffect(() => {
    if (isLoading || !profile)
      return
    if (!isAgent && status !== 'active') {
      // Not an agent at all OR suspended — kick to /apps with a Toast.
      if (status === 'suspended')
        toast.warning(t('agent:guard.suspended'))
      router.replace('/apps')
    }
  }, [isLoading, profile, isAgent, status, router, t])

  if (isLoading || !profile || !isAgent || status !== 'active')
    return null

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background-body">
      <header className="flex shrink-0 items-center justify-between border-b border-divider-subtle bg-background-default px-6 py-3">
        <div className="flex items-center gap-6">
          <h1 className="text-base font-semibold text-text-primary">
            {t('agent:console.title')}
          </h1>
          <nav className="flex items-center gap-2">
            {NAV_ITEMS.map((item) => {
              const active = pathname?.startsWith(item.href) ?? false
              return (
                <button
                  key={item.href}
                  type="button"
                  onClick={() => router.push(item.href)}
                  className={`rounded-md px-3 py-1.5 text-sm transition ${
                    active
                      ? 'bg-state-accent-active text-text-accent'
                      : 'text-text-secondary hover:bg-state-base-hover'
                  }`}
                >
                  {t(`agent:${item.key}`)}
                </button>
              )
            })}
          </nav>
        </div>
        <button
          type="button"
          onClick={() => router.push('/apps')}
          className="rounded-md border border-components-button-secondary-border px-3 py-1.5 text-sm text-text-secondary hover:bg-state-base-hover"
        >
          {t('agent:console.backToApp')}
        </button>
      </header>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  )
}

export default AgentLayout
