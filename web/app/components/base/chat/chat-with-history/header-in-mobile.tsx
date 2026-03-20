import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import ActionButton from '@/app/components/base/action-button'
import AppIcon from '@/app/components/base/app-icon'
import InputsFormContent from '@/app/components/base/chat/chat-with-history/inputs-form/content'
import { useChatWithHistoryContext } from './context'
import MobileOperationDropdown from './header/mobile-operation-dropdown'
import Sidebar from './sidebar'

const HeaderInMobile = () => {
  const {
    appData,
    handleNewConversation,
    inputsForms,
  } = useChatWithHistoryContext()
  const { t } = useTranslation()
  const [showSidebar, setShowSidebar] = useState(false)
  const [showChatSettings, setShowChatSettings] = useState(false)

  return (
    <>
      <div className="flex shrink-0 items-center gap-1 bg-mask-top2bottom-gray-50-to-transparent px-2 py-3">
        <ActionButton size="l" className="shrink-0" onClick={() => setShowSidebar(true)}>
          <div className="i-ri-menu-line h-[18px] w-[18px]" />
        </ActionButton>
        <div className="flex grow items-center justify-center">
          <AppIcon
            className="mr-2"
            size="tiny"
            icon={appData?.site.icon}
            iconType={appData?.site.icon_type}
            imageUrl={appData?.site.icon_url}
            background={appData?.site.icon_background}
          />
          <div className="truncate text-text-secondary system-md-semibold">
            {appData?.site.title}
          </div>
        </div>
        <MobileOperationDropdown
          handleResetChat={handleNewConversation}
          handleViewChatSettings={() => setShowChatSettings(true)}
          hideViewChatSettings={inputsForms.length < 1}
        />
      </div>
      {showSidebar && (
        <div
          className="fixed inset-0 z-50 flex bg-background-overlay p-1"
          onClick={() => setShowSidebar(false)}
          data-testid="mobile-sidebar-overlay"
        >
          <div className="flex h-full w-[calc(100vw_-_40px)] rounded-xl bg-components-panel-bg shadow-lg backdrop-blur-sm" onClick={e => e.stopPropagation()} data-testid="sidebar-content">
            <Sidebar />
          </div>
        </div>
      )}
      {showChatSettings && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-background-overlay p-1"
          onClick={() => setShowChatSettings(false)}
          data-testid="mobile-chat-settings-overlay"
        >
          <div className="flex h-full w-[calc(100vw_-_40px)] flex-col rounded-xl bg-components-panel-bg shadow-lg backdrop-blur-sm" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 rounded-t-2xl border-b border-divider-subtle px-4 py-3">
              <div className="i-custom-public-other-message-3-fill h-6 w-6 shrink-0" />
              <div className="grow text-text-secondary system-xl-semibold">{t('chat.chatSettingsTitle', { ns: 'share' })}</div>
            </div>
            <div className="p-4">
              <InputsFormContent />
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default HeaderInMobile
