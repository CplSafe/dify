'use client'

import { useMemo, useState } from 'react'
import Button from '@/app/components/base/button'
import { ScrollArea } from '@/app/components/base/ui/scroll-area'
import MenuDialog from '@/app/components/header/account-setting/menu-dialog'
import { useAppContext } from '@/context/app-context'
import { cn } from '@/utils/classnames'
import AccountTab from './tabs/account-tab'
import ApiKeyTab from './tabs/api-key-tab'
import BalanceTab from './tabs/balance-tab'
import InvitationTab from './tabs/invitation-tab'
import MembersTab from './tabs/members-tab'
import RebateTab from './tabs/rebate-tab'

export type CreatorSettingsTab
  = | 'account'
    | 'members'
    | 'balance'
    | 'api-key'
    | 'invitation'
    | 'rebate'

type MenuItem = {
  key: CreatorSettingsTab
  label: string
  iconClass: string
  activeIconClass: string
  // When true, the tab is only meaningful for workspace owners — members
  // can neither create invite codes nor receive rebates.
  ownerOnly?: boolean
  // 产品侧临时隐藏该 tab。保留菜单定义、Tab 组件和路由分支，日后把
  // hidden 去掉即可恢复。后端接口仍然可用，不受影响。
  hidden?: boolean
}

const MENU_ITEMS: MenuItem[] = [
  {
    key: 'account',
    label: '账户设置',
    iconClass: 'i-ri-account-circle-line',
    activeIconClass: 'i-ri-account-circle-fill',
  },
  {
    key: 'members',
    label: '成员管理',
    iconClass: 'i-ri-group-2-line',
    activeIconClass: 'i-ri-group-2-fill',
    ownerOnly: true,
  },
  {
    key: 'balance',
    label: '余额账单',
    iconClass: 'i-ri-wallet-3-line',
    activeIconClass: 'i-ri-wallet-3-fill',
  },
  {
    key: 'api-key',
    label: 'API Key',
    iconClass: 'i-ri-key-2-line',
    activeIconClass: 'i-ri-key-2-fill',
  },
  {
    key: 'invitation',
    label: '邀请管理',
    iconClass: 'i-ri-user-add-line',
    activeIconClass: 'i-ri-user-add-fill',
    ownerOnly: true,
    hidden: true,
  },
  {
    key: 'rebate',
    label: '返点账单',
    iconClass: 'i-ri-money-cny-circle-line',
    activeIconClass: 'i-ri-money-cny-circle-fill',
    ownerOnly: true,
  },
]

type Props = {
  show: boolean
  defaultTab?: CreatorSettingsTab
  onClose: () => void
}

export default function CreatorSettingsModal({
  show,
  defaultTab = 'account',
  onClose,
}: Props) {
  const { isCurrentWorkspaceOwner } = useAppContext()
  // Members see a reduced menu. Hiding instead of disabling keeps the UI
  // clean — members never have anything to do on these tabs — and the
  // backend also returns 403, so even a deep-link to an owner-only tab
  // won't load data.
  const visibleMenuItems = useMemo(
    () =>
      MENU_ITEMS.filter(
        item => !item.hidden && (!item.ownerOnly || isCurrentWorkspaceOwner),
      ),
    [isCurrentWorkspaceOwner],
  )
  const fallbackTab: CreatorSettingsTab
    = visibleMenuItems.find(m => m.key === defaultTab)?.key ?? 'account'
  const [selectedTab, setSelectedTab]
    = useState<CreatorSettingsTab>(fallbackTab)

  // Derive the rendered tab instead of syncing through an effect: if the
  // user picked a tab that later becomes hidden (e.g. role downgrade,
  // modal reopened with a different defaultTab) we silently fall back.
  // A member opening the modal via "账户设置" must not land on whatever
  // the previous owner session last picked.
  const activeTab = visibleMenuItems.find(m => m.key === selectedTab)
    ? selectedTab
    : fallbackTab
  const activeItem = visibleMenuItems.find(m => m.key === activeTab)

  return (
    <MenuDialog show={show} onClose={onClose}>
      <div className="mx-auto flex h-screen max-w-[1048px]">
        {/* Left sidebar */}
        <div className="flex w-[44px] flex-col border-r border-divider-burn pr-6 pl-4 sm:w-[224px]">
          <div className="mt-6 mb-8 px-3 py-2 title-2xl-semi-bold text-text-primary">
            设置
          </div>
          <div className="w-full">
            <div className="mb-0.5 py-2 pb-1 pl-3 system-xs-medium-uppercase text-text-tertiary">
              工作区
            </div>
            {visibleMenuItems.map(item => (
              <button
                key={item.key}
                type="button"
                onClick={() => setSelectedTab(item.key)}
                className={cn(
                  'mb-0.5 flex h-[37px] w-full items-center rounded-lg p-1 pl-3 text-left',
                  activeTab === item.key
                    ? 'bg-state-base-active system-sm-semibold text-components-menu-item-text-active'
                    : 'system-sm-medium text-components-menu-item-text',
                )}
              >
                <span
                  className={cn(
                    'mr-2 h-5 w-5',
                    activeTab === item.key
                      ? item.activeIconClass
                      : item.iconClass,
                  )}
                />
                <span className="hidden truncate sm:block">{item.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Right content panel */}
        <div className="relative flex min-h-0 w-[824px]">
          <div className="fixed top-6 right-6 z-[9999] flex flex-col items-center">
            <Button
              variant="tertiary"
              size="large"
              className="px-2"
              aria-label="关闭"
              onClick={onClose}
            >
              <span className="i-ri-close-line h-5 w-5" />
            </Button>
            <div className="mt-1 system-2xs-medium-uppercase text-text-tertiary">
              ESC
            </div>
          </div>

          <ScrollArea
            className="h-full min-h-0 flex-1 bg-components-panel-bg"
            slotClassNames={{
              viewport: 'overscroll-contain',
              content: 'min-h-full pb-4',
            }}
          >
            <div className="sticky top-0 z-20 mx-8 mb-[18px] bg-components-panel-bg pt-[27px] pb-2">
              <div className="title-2xl-semi-bold text-text-primary">
                {activeItem?.label}
              </div>
            </div>

            <div className="px-4 pt-2 sm:px-8">
              {activeTab === 'account' && <AccountTab />}
              {activeTab === 'members' && <MembersTab />}
              {activeTab === 'balance' && <BalanceTab />}
              {activeTab === 'api-key' && <ApiKeyTab />}
              {activeTab === 'invitation' && <InvitationTab />}
              {activeTab === 'rebate' && <RebateTab />}
            </div>
          </ScrollArea>
        </div>
      </div>
    </MenuDialog>
  )
}
