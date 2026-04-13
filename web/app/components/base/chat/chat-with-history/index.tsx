'use client'
import type { FC } from 'react'
import type { CreatorChatDraft } from '@/app/components/creator/chat-draft'
import type { GeneratedResultPayload } from '@/app/components/share/generated-result'
import type { InstalledApp } from '@/models/explore'
import { useEffect, useState } from 'react'
import Loading from '@/app/components/base/loading'
import useBreakpoints, { MediaType } from '@/hooks/use-breakpoints'
import useDocumentTitle from '@/hooks/use-document-title'
import { cn } from '@/utils/classnames'
import { useThemeContext } from '../embedded-chatbot/theme/theme-context'
import ChatWrapper from './chat-wrapper'
import { ChatWithHistoryContext, useChatWithHistoryContext } from './context'
import Header from './header'
import HeaderInMobile from './header-in-mobile'
import { useChatWithHistory } from './hooks'
import Sidebar from './sidebar'

type ChatWithHistoryProps = {
  className?: string
  initialDraft?: CreatorChatDraft | null
  onInitialDraftConsumed?: () => void
  onMessageCompleted?: (
    payload: GeneratedResultPayload,
  ) => void | Promise<void>
  onMessageStart?: (params: {
    installedAppId: string
    conversationId: string | null
  }) => void
}
const ChatWithHistory: FC<ChatWithHistoryProps> = ({
  className,
  initialDraft,
  onInitialDraftConsumed,
  onMessageCompleted,
  onMessageStart,
}) => {
  const {
    appData,
    appChatListDataLoading,
    chatShouldReloadKey,
    isMobile,
    themeBuilder,
    sidebarCollapseState,
  } = useChatWithHistoryContext()
  const isSidebarCollapsed = sidebarCollapseState
  const hideAppCenter = true
  const customConfig = appData?.custom_config
  const site = appData?.site
  const chatPageBackgroundStyle = site?.chat_page_background_color
    ? { backgroundColor: site.chat_page_background_color }
    : undefined
  const hasCustomChatPageBackground = !!site?.chat_page_background_color

  const [showSidePanel, setShowSidePanel] = useState(false)

  useEffect(() => {
    themeBuilder?.buildTheme(
      site?.chat_color_theme,
      site?.chat_color_theme_inverted,
    )
  }, [site, customConfig, themeBuilder])

  useEffect(() => {
    if (!isSidebarCollapsed)
      setShowSidePanel(false)
  }, [isSidebarCollapsed])

  useDocumentTitle(site?.title || 'Chat')

  return (
    <div
      className={cn(
        'flex h-full bg-background-default-burn',
        isMobile && 'flex-col',
        className,
      )}
      style={chatPageBackgroundStyle}
    >
      {!isMobile && !hideAppCenter && (
        <div
          className={cn(
            'flex w-[236px] flex-col p-1 pr-0 transition-all duration-200 ease-in-out',
            isSidebarCollapsed && 'w-0 overflow-hidden p-0!',
          )}
        >
          <Sidebar />
        </div>
      )}
      {isMobile && !hideAppCenter && <HeaderInMobile />}
      <div
        className={cn(
          'relative grow p-2',
          isMobile && !hideAppCenter && 'h-[calc(100%-56px)] p-0',
          hideAppCenter && 'p-0',
        )}
      >
        {isSidebarCollapsed && !hideAppCenter && (
          <div
            className={cn(
              'absolute top-0 z-20 flex h-full w-[256px] flex-col p-2 transition-all duration-500 ease-in-out',
              showSidePanel ? 'left-0' : 'left-[-248px]',
            )}
            onMouseEnter={() => setShowSidePanel(true)}
            onMouseLeave={() => setShowSidePanel(false)}
          >
            <Sidebar isPanel panelVisible={showSidePanel} />
          </div>
        )}
        <div
          className={cn(
            'flex h-full flex-col overflow-hidden border-[0,5px] border-components-panel-border-subtle',
            !hasCustomChatPageBackground && 'bg-chatbot-bg',
            isMobile ? 'rounded-t-2xl' : 'rounded-2xl',
          )}
          style={chatPageBackgroundStyle}
        >
          {!isMobile && !hideAppCenter && <Header />}
          {appChatListDataLoading && <Loading type="app" />}
          {!appChatListDataLoading && (
            <ChatWrapper
              key={chatShouldReloadKey}
              initialDraft={initialDraft}
              onInitialDraftConsumed={onInitialDraftConsumed}
              onMessageCompleted={onMessageCompleted}
              onMessageStart={onMessageStart}
            />
          )}
        </div>
      </div>
    </div>
  )
}

type ChatWithHistoryWrapProps = {
  installedAppInfo?: InstalledApp
  className?: string
  initialDraft?: CreatorChatDraft | null
  forceFreshConversation?: boolean
  onInitialDraftConsumed?: () => void
  onMessageCompleted?: (
    payload: GeneratedResultPayload,
  ) => void | Promise<void>
  onMessageStart?: (params: {
    installedAppId: string
    conversationId: string | null
  }) => void
}
const ChatWithHistoryWrap: FC<ChatWithHistoryWrapProps> = ({
  installedAppInfo,
  className,
  initialDraft,
  forceFreshConversation,
  onInitialDraftConsumed,
  onMessageCompleted,
  onMessageStart,
}) => {
  const media = useBreakpoints()
  const isMobile = media === MediaType.mobile
  const themeBuilder = useThemeContext()

  const {
    appData,
    appParams,
    appMeta,
    appChatListDataLoading,
    currentConversationId,
    currentConversationItem,
    appPrevChatTree,
    pinnedConversationList,
    conversationList,
    newConversationInputs,
    newConversationInputsRef,
    handleNewConversationInputsChange,
    inputsForms,
    handleNewConversation,
    handleStartChat,
    handleChangeConversation,
    handlePinConversation,
    handleUnpinConversation,
    handleDeleteConversation,
    conversationRenaming,
    handleRenameConversation,
    handleNewConversationCompleted,
    chatShouldReloadKey,
    isInstalledApp,
    appId,
    handleFeedback,
    currentChatInstanceRef,
    sidebarCollapseState,
    handleSidebarCollapse,
    clearChatList,
    setClearChatList,
    isResponding,
    setIsResponding,
    currentConversationInputs,
    setCurrentConversationInputs,
    allInputsHidden,
    initUserVariables,
  } = useChatWithHistory(installedAppInfo, forceFreshConversation)

  return (
    <ChatWithHistoryContext.Provider
      value={{
        appData,
        appParams,
        appMeta,
        appChatListDataLoading,
        currentConversationId,
        currentConversationItem,
        appPrevChatTree,
        pinnedConversationList,
        conversationList,
        newConversationInputs,
        newConversationInputsRef,
        handleNewConversationInputsChange,
        inputsForms,
        handleNewConversation,
        handleStartChat,
        handleChangeConversation,
        handlePinConversation,
        handleUnpinConversation,
        handleDeleteConversation,
        conversationRenaming,
        handleRenameConversation,
        handleNewConversationCompleted,
        chatShouldReloadKey,
        isMobile,
        isInstalledApp,
        appId,
        handleFeedback,
        currentChatInstanceRef,
        themeBuilder,
        sidebarCollapseState,
        handleSidebarCollapse,
        clearChatList,
        setClearChatList,
        isResponding,
        setIsResponding,
        currentConversationInputs,
        setCurrentConversationInputs,
        allInputsHidden,
        initUserVariables,
      }}
    >
      <ChatWithHistory
        className={className}
        initialDraft={initialDraft}
        onInitialDraftConsumed={onInitialDraftConsumed}
        onMessageCompleted={onMessageCompleted}
        onMessageStart={onMessageStart}
      />
    </ChatWithHistoryContext.Provider>
  )
}

const ChatWithHistoryWrapWithCheckToken: FC<ChatWithHistoryWrapProps> = ({
  installedAppInfo,
  className,
  initialDraft,
  forceFreshConversation,
  onInitialDraftConsumed,
  onMessageCompleted,
  onMessageStart,
}) => {
  return (
    <ChatWithHistoryWrap
      installedAppInfo={installedAppInfo}
      className={className}
      initialDraft={initialDraft}
      forceFreshConversation={forceFreshConversation}
      onInitialDraftConsumed={onInitialDraftConsumed}
      onMessageCompleted={onMessageCompleted}
      onMessageStart={onMessageStart}
    />
  )
}

export default ChatWithHistoryWrapWithCheckToken
