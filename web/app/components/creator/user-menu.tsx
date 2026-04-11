'use client'

import { useCallback, useEffect, useState } from 'react'
import { RiLoader4Line, RiLogoutBoxRLine, RiTeamLine, RiUserLine, RiWalletLine, RiDashboardLine } from '@remixicon/react'
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/app/components/base/ui/dropdown-menu'
import { useAppContext } from '@/context/app-context'
import { get } from '@/service/base'
import { useLogout } from '@/service/use-common'
import { useRouter } from '@/next/navigation'
import { cn } from '@/utils/classnames'
import CreatorSettingsModal from './settings/creator-settings-modal'
import type { CreatorSettingsTab } from './settings/creator-settings-modal'

type Balance = {
  balance: string
  currency: string
  is_sufficient: boolean
}

export default function CreatorUserMenu() {
  const { userProfile, isSystemAdmin } = useAppContext()
  const router = useRouter()
  const { mutateAsync: logout } = useLogout()

  const [balance, setBalance] = useState<Balance | null>(null)
  const [balanceLoading, setBalanceLoading] = useState(true)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsTab, setSettingsTab] = useState<CreatorSettingsTab>('account')

  const loadBalance = useCallback(() => {
    setBalanceLoading(true)
    get<Balance>('/creator/balance')
      .then(setBalance)
      .catch(() => {})
      .finally(() => setBalanceLoading(false))
  }, [])

  useEffect(() => {
    loadBalance()
  }, [loadBalance])

  useEffect(() => {
    const handleFocus = () => {
      loadBalance()
    }

    const intervalId = globalThis.setInterval(() => {
      loadBalance()
    }, 15000)

    globalThis.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleFocus)

    return () => {
      globalThis.clearInterval(intervalId)
      globalThis.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleFocus)
    }
  }, [loadBalance])

  const openSettings = (tab: CreatorSettingsTab) => {
    setSettingsTab(tab)
    setSettingsOpen(true)
  }

  const handleLogout = async () => {
    await logout()
    localStorage.removeItem('setup_status')
    router.push('/signin')
  }

  const avatarLetter = userProfile?.name?.charAt(0)?.toUpperCase() || 'U'

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-state-base-hover"
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100 text-sm font-semibold text-primary-700">
              {avatarLetter}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-text-primary">{userProfile?.name || '用户'}</div>
              <div className="flex items-center gap-1">
                {balanceLoading
                  ? <RiLoader4Line className="h-3 w-3 animate-spin text-text-quaternary" />
                  : balance
                    ? (
                        <span className={cn(
                          'text-xs font-medium',
                          balance.is_sufficient ? 'text-state-success-text' : 'text-state-destructive-text',
                        )}>
                          {Number(balance.balance).toFixed(2)} {balance.currency}
                        </span>
                      )
                    : <span className="text-xs text-text-quaternary">{userProfile?.email || ''}</span>}
              </div>
            </div>
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent side="top" align="start" sideOffset={8} popupClassName="w-52 py-0!">
          {/* User info header */}
          <div className="px-3 py-3">
            <div className="text-sm font-medium text-text-primary">{userProfile?.name}</div>
            <div className="text-xs text-text-quaternary">{userProfile?.email}</div>
            {balance && (
              <div className={cn(
                'mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
                balance.is_sufficient
                  ? 'bg-state-success-hover text-state-success-text'
                  : 'bg-state-destructive-hover text-state-destructive-text',
              )}>
                <RiWalletLine className="h-3 w-3" />
                {Number(balance.balance).toFixed(2)} {balance.currency}
              </div>
            )}
          </div>

          <DropdownMenuSeparator className="my-0! bg-divider-subtle" />

          <DropdownMenuGroup className="py-1">
            <DropdownMenuItem onClick={() => openSettings('account')}>
              <RiUserLine className="mr-2 h-4 w-4 text-text-tertiary" />
              账户设置
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => openSettings('members')}>
              <RiTeamLine className="mr-2 h-4 w-4 text-text-tertiary" />
              成员管理
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => openSettings('balance')}>
              <RiWalletLine className="mr-2 h-4 w-4 text-text-tertiary" />
              余额账单
            </DropdownMenuItem>
          </DropdownMenuGroup>

          <DropdownMenuSeparator className="my-0! bg-divider-subtle" />

          {isSystemAdmin && (
            <>
              <DropdownMenuGroup className="py-1">
                <DropdownMenuItem onClick={() => router.push('/apps')}>
                  <RiDashboardLine className="mr-2 h-4 w-4 text-text-tertiary" />
                  返回管理平台
                </DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator className="my-0! bg-divider-subtle" />
            </>
          )}
          <DropdownMenuGroup className="py-1">
            <DropdownMenuItem onClick={() => void handleLogout()}>
              <RiLogoutBoxRLine className="mr-2 h-4 w-4 text-text-tertiary" />
              退出登录
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      <CreatorSettingsModal
        show={settingsOpen}
        defaultTab={settingsTab}
        onClose={() => {
          setSettingsOpen(false)
          // Refresh balance after closing (in case topup happened)
          loadBalance()
        }}
      />
    </>
  )
}
