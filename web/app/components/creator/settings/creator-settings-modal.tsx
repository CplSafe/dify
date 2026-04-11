'use client'

import { useEffect, useState } from 'react'
import Button from '@/app/components/base/button'
import { ScrollArea } from '@/app/components/base/ui/scroll-area'
import MenuDialog from '@/app/components/header/account-setting/menu-dialog'
import { cn } from '@/utils/classnames'
import AccountTab from './tabs/account-tab'
import ApiKeyTab from './tabs/api-key-tab'
import BalanceTab from './tabs/balance-tab'
import InvitationTab from './tabs/invitation-tab'
import MembersTab from './tabs/members-tab'
import RebateTab from './tabs/rebate-tab'

export type CreatorSettingsTab = 'account' | 'members' | 'balance' | 'api-key' | 'invitation' | 'rebate'

type MenuItem = {
  key: CreatorSettingsTab
  label: string
  iconClass: string
  activeIconClass: string
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
  },
  {
    key: 'rebate',
    label: '返点账单',
    iconClass: 'i-ri-money-cny-circle-line',
    activeIconClass: 'i-ri-money-cny-circle-fill',
  },
]

type Props = {
  show: boolean
  defaultTab?: CreatorSettingsTab
  onClose: () => void
}

export default function CreatorSettingsModal({ show, defaultTab = 'account', onClose }: Props) {
  const [activeTab, setActiveTab] = useState<CreatorSettingsTab>(defaultTab)

  useEffect(() => {
    if (show)
      setActiveTab(defaultTab)
  }, [show, defaultTab])

  const activeItem = MENU_ITEMS.find(m => m.key === activeTab)

  return (
    <MenuDialog show={show} onClose={onClose}>
      <div className="mx-auto flex h-screen max-w-[1048px]">
        {/* Left sidebar */}
        <div className="flex w-[44px] flex-col border-r border-divider-burn pl-4 pr-6 sm:w-[224px]">
          <div className="mb-8 mt-6 px-3 py-2 text-text-primary title-2xl-semi-bold">设置</div>
          <div className="w-full">
            <div className="mb-0.5 py-2 pb-1 pl-3 text-text-tertiary system-xs-medium-uppercase">工作区</div>
            {MENU_ITEMS.map(item => (
              <button
                key={item.key}
                type="button"
                onClick={() => setActiveTab(item.key)}
                className={cn(
                  'mb-0.5 flex h-[37px] w-full items-center rounded-lg p-1 pl-3 text-left',
                  activeTab === item.key
                    ? 'bg-state-base-active text-components-menu-item-text-active system-sm-semibold'
                    : 'text-components-menu-item-text system-sm-medium',
                )}
              >
                <span className={cn('mr-2 h-5 w-5', activeTab === item.key ? item.activeIconClass : item.iconClass)} />
                <span className="hidden truncate sm:block">{item.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Right content panel */}
        <div className="relative flex min-h-0 w-[824px]">
          <div className="fixed right-6 top-6 z-[9999] flex flex-col items-center">
            <Button variant="tertiary" size="large" className="px-2" aria-label="关闭" onClick={onClose}>
              <span className="i-ri-close-line h-5 w-5" />
            </Button>
            <div className="mt-1 text-text-tertiary system-2xs-medium-uppercase">ESC</div>
          </div>

          <ScrollArea
            className="h-full min-h-0 flex-1 bg-components-panel-bg"
            slotClassNames={{ viewport: 'overscroll-contain', content: 'min-h-full pb-4' }}
          >
            <div className="sticky top-0 z-20 mx-8 mb-[18px] bg-components-panel-bg pb-2 pt-[27px]">
              <div className="text-text-primary title-2xl-semi-bold">{activeItem?.label}</div>
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
