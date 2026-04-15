'use client'
/* eslint-disable tailwindcss/enforce-consistent-class-order -- TODO(wallet): preexisting issues tracked for a follow-up cleanup */

import type { CreatorSettingsTab } from './settings/creator-settings-modal'
import {
  RiAddCircleLine,
  RiDashboardLine,
  RiFileList3Line,
  RiLoader4Line,
  RiLogoutBoxRLine,
  RiTeamLine,
  RiUserLine,
  RiWalletLine,
} from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/app/components/base/ui/dropdown-menu'
import { useAppContext } from '@/context/app-context'
import { useRouter } from '@/next/navigation'
import { get } from '@/service/base'
import { useLogout } from '@/service/use-common'
import { cn } from '@/utils/classnames'
import CreatorSettingsModal from './settings/creator-settings-modal'
import TopupModal from './wallet/topup-modal'

type Balance = {
  balance: string
  currency: string
  is_sufficient: boolean
}

type CreatorUserMenuProps = {
  collapsed?: boolean
}

export default function CreatorUserMenu({
  collapsed = false,
}: CreatorUserMenuProps) {
  const { userProfile, isSystemAdmin, isCurrentWorkspaceOwner }
    = useAppContext()
  const router = useRouter()
  const { mutateAsync: logout } = useLogout()

  const [balance, setBalance] = useState<Balance | null>(null)
  const [balanceLoading, setBalanceLoading] = useState(true)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsTab, setSettingsTab] = useState<CreatorSettingsTab>('account')
  const [topupOpen, setTopupOpen] = useState(false)

  // Re-bind balance to the current account: when the user logs out and
  // back in as someone else, ``userProfile.id`` flips, which both
  // (a) wipes the previous numeric balance from view (no stale flash) and
  // (b) triggers a fresh fetch keyed to the new identity. Without the
  // explicit reset, ``setBalance`` retains the previous user's value
  // until the new fetch resolves.
  const accountId = userProfile?.id
  const loadBalance = useCallback(() => {
    if (!accountId) {
      // eslint-disable-next-line react/set-state-in-effect
      setBalance(null)
      // eslint-disable-next-line react/set-state-in-effect
      setBalanceLoading(false)
      return
    }
    // eslint-disable-next-line react/set-state-in-effect
    setBalance(null)
    // eslint-disable-next-line react/set-state-in-effect
    setBalanceLoading(true)
    get<Balance>('/creator/balance')
      .then(setBalance)
      .catch(() => {})
      // eslint-disable-next-line react/set-state-in-effect
      .finally(() => setBalanceLoading(false))
  }, [accountId])

  useEffect(() => {
    loadBalance()
  }, [loadBalance])

  useEffect(() => {
    const handleFocus = () => {
      loadBalance()
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible')
        loadBalance()
    }

    globalThis.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      globalThis.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
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
        <DropdownMenuTrigger
          aria-label={collapsed ? userProfile?.name || '用户菜单' : undefined}
          title={collapsed ? userProfile?.name || '用户' : undefined}
          className={cn(
            'group flex w-full cursor-default items-center rounded-xl text-left transition-colors hover:bg-black/[0.04] active:bg-black/[0.06]',
            collapsed ? 'justify-center p-2' : 'gap-3 py-2.5 pr-3 pl-2.5',
          )}
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#4D80FF] to-[#B98DFF] text-sm font-bold text-white">
            {avatarLetter}
          </div>
          {!collapsed && (
            <div className="min-w-0 flex-1 text-left">
              <div className="truncate text-sm font-semibold text-text-primary">
                {userProfile?.name || '用户'}
              </div>
              <div className="mt-0.5 flex items-center gap-1.5">
                {balanceLoading
                  ? (
                      <RiLoader4Line className="h-3 w-3 animate-spin text-text-quaternary" />
                    )
                  : balance
                    ? (
                        <span
                          className={cn(
                            'rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums',
                            balance.is_sufficient
                              ? 'bg-primary-50 text-primary-700'
                              : 'bg-state-destructive-hover text-state-destructive-text',
                          )}
                        >
                          {Number(balance.balance).toFixed(2)}
                          {' '}
                          {balance.currency}
                        </span>
                      )
                    : (
                        <span className="truncate text-xs text-text-tertiary">
                          {userProfile?.email || ''}
                        </span>
                      )}
              </div>
            </div>
          )}
        </DropdownMenuTrigger>

        <DropdownMenuContent
          placement="top-start"
          sideOffset={8}
          popupClassName="w-52 py-0!"
        >
          {/* User info header */}
          <div className="px-3 py-3">
            <div className="truncate text-sm font-medium text-text-primary">
              {userProfile?.name}
            </div>
            <div className="truncate text-xs text-text-tertiary">
              {userProfile?.email}
            </div>
          </div>

          <DropdownMenuSeparator className="my-0! bg-divider-subtle" />

          {isCurrentWorkspaceOwner && (
            <>
              <DropdownMenuGroup className="py-1">
                <DropdownMenuItem
                  onClick={() => setTopupOpen(true)}
                  className={cn(
                    balance
                    && !balance.is_sufficient
                    && 'bg-state-warning-hover/40',
                  )}
                >
                  <RiAddCircleLine className="mr-2 h-4 w-4 text-primary-600" />
                  <span className="font-medium text-text-primary">充值</span>
                  {balance && (
                    <span
                      className={cn(
                        'ml-auto text-xs tabular-nums',
                        balance.is_sufficient
                          ? 'text-text-tertiary'
                          : 'font-medium text-state-destructive-text',
                      )}
                    >
                      {Number(balance.balance).toFixed(2)}
                    </span>
                  )}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => router.push('/creator/wallet/orders')}
                >
                  <RiFileList3Line className="mr-2 h-4 w-4 text-text-tertiary" />
                  <span className="font-medium text-text-primary">
                    充值订单
                  </span>
                </DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator className="my-0! bg-divider-subtle" />
            </>
          )}

          <DropdownMenuGroup className="py-1">
            <DropdownMenuItem onClick={() => openSettings('account')}>
              <RiUserLine className="mr-2 h-4 w-4 text-text-tertiary" />
              账户设置
            </DropdownMenuItem>
            {isCurrentWorkspaceOwner && (
              <DropdownMenuItem onClick={() => openSettings('members')}>
                <RiTeamLine className="mr-2 h-4 w-4 text-text-tertiary" />
                成员管理
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => openSettings('balance')}>
              <RiWalletLine className="mr-2 h-4 w-4 text-text-tertiary" />
              余额账单
            </DropdownMenuItem>
          </DropdownMenuGroup>

          <DropdownMenuSeparator className="my-0! bg-divider-subtle" />

          {isSystemAdmin && (
            <>
              <DropdownMenuGroup className="py-1">
                <DropdownMenuItem
                  onClick={() => router.push('/creator/admin/topup-orders')}
                >
                  <RiFileList3Line className="mr-2 h-4 w-4 text-text-tertiary" />
                  支付订单（超管）
                </DropdownMenuItem>
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

      <TopupModal
        open={topupOpen}
        onOpenChange={setTopupOpen}
        onPaid={loadBalance}
      />
    </>
  )
}
