import {
  RiEditBoxLine,
  RiLayoutRight2Line,
  RiResetLeftLine,
} from '@remixicon/react'
import { useTranslation } from 'react-i18next'
import ActionButton, { ActionButtonState } from '@/app/components/base/action-button'
import AppIcon from '@/app/components/base/app-icon'
import ViewFormDropdown from '@/app/components/base/chat/chat-with-history/inputs-form/view-form-dropdown'
import Tooltip from '@/app/components/base/tooltip'
import { cn } from '@/utils/classnames'
import {
  useChatWithHistoryContext,
} from '../context'

const Header = () => {
  const {
    appData,
    currentConversationId,
    inputsForms,
    handleNewConversation,
    sidebarCollapseState,
    handleSidebarCollapse,
    isResponding,
  } = useChatWithHistoryContext()
  const { t } = useTranslation()
  const isSidebarCollapsed = sidebarCollapseState

  return (
    <>
      <div className="flex h-14 shrink-0 items-center justify-between p-3">
        <div className={cn('flex items-center gap-1 transition-all duration-200 ease-in-out', !isSidebarCollapsed && 'user-select-none opacity-0')}>
          <ActionButton className={cn(!isSidebarCollapsed && 'cursor-default')} size="l" onClick={() => handleSidebarCollapse(false)}>
            <RiLayoutRight2Line className="h-[18px] w-[18px]" />
          </ActionButton>
          <div className="mr-1 shrink-0">
            <AppIcon
              size="large"
              iconType={appData?.site.icon_type}
              icon={appData?.site.icon}
              background={appData?.site.icon_background}
              imageUrl={appData?.site.icon_url}
            />
          </div>
          <div className={cn('grow truncate text-text-secondary system-md-semibold')}>{appData?.site.title}</div>
          <div className="flex items-center px-1">
            <div className="h-[14px] w-px bg-divider-regular"></div>
          </div>
          {isSidebarCollapsed && (
            <Tooltip
              disabled={!!currentConversationId}
              popupContent={t('chat.newChatTip', { ns: 'share' })}
            >
              <div>
                <ActionButton
                  size="l"
                  state={(!currentConversationId || isResponding) ? ActionButtonState.Disabled : ActionButtonState.Default}
                  disabled={!currentConversationId || isResponding}
                  onClick={handleNewConversation}
                >
                  <RiEditBoxLine className="h-[18px] w-[18px]" />
                </ActionButton>
              </div>
            </Tooltip>
          )}
        </div>
        <div className="flex items-center gap-1">
          {currentConversationId && (
            <Tooltip
              popupContent={t('chat.resetChat', { ns: 'share' })}
            >
              <ActionButton size="l" onClick={handleNewConversation}>
                <RiResetLeftLine className="h-[18px] w-[18px]" />
              </ActionButton>
            </Tooltip>
          )}
          {currentConversationId && inputsForms.length > 0 && (
            <ViewFormDropdown />
          )}
        </div>
      </div>
    </>
  )
}

export default Header
