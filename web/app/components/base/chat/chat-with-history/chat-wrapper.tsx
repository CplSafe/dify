import type { FileEntity } from '../../file-uploader/types'
import type {
  ChatConfig,
  ChatItem,
  ChatItemInTree,
  OnSend,
} from '../types'
import type { FileUpload } from '@/app/components/base/features/types'
import type { GeneratedResultPayload } from '@/app/components/share/generated-result'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import AnswerIcon from '@/app/components/base/answer-icon'
import AppIcon from '@/app/components/base/app-icon'
import InputsForm from '@/app/components/base/chat/chat-with-history/inputs-form'
import SuggestedQuestions from '@/app/components/base/chat/chat/answer/suggested-questions'
import ChatInputArea from '@/app/components/base/chat/chat/chat-input-area'
import { FeaturesProvider } from '@/app/components/base/features/context'
import { Markdown } from '@/app/components/base/markdown'
import { FILE_EXTS } from '@/app/components/base/prompt-editor/constants'
import { InputVarType, SupportUploadFileTypes } from '@/app/components/workflow/types'
import {
  AppSourceType,
  fetchChatList,
  fetchSuggestedQuestions,
  getUrl,
  stopChatMessageResponding,
  submitHumanInputForm,
} from '@/service/share'
import { submitHumanInputForm as submitHumanInputFormService } from '@/service/workflow'
import { Resolution, TransferMethod } from '@/types/app'
import { cn } from '@/utils/classnames'
import { formatBooleanInputs } from '@/utils/model-config'
import { Avatar } from '../../avatar'
import Chat from '../chat'
import { useChat } from '../chat/hooks'
import { getLastAnswer, isValidGeneratedAnswer } from '../utils'
import { useChatWithHistoryContext } from './context'

const ChatWrapper = ({
  onMessageCompleted,
}: {
  onMessageCompleted?: (payload: GeneratedResultPayload) => void | Promise<void>
}) => {
  const { t } = useTranslation()
  const {
    appParams,
    appPrevChatTree,
    currentConversationId,
    currentConversationItem,
    currentConversationInputs,
    inputsForms,
    newConversationInputs,
    newConversationInputsRef,
    handleNewConversationCompleted,
    isMobile,
    isInstalledApp,
    appId,
    appMeta,
    handleFeedback,
    currentChatInstanceRef,
    appData,
    themeBuilder,
    sidebarCollapseState,
    clearChatList,
    setClearChatList,
    setIsResponding,
    allInputsHidden,
    initUserVariables,
  } = useChatWithHistoryContext()
  const appSourceType = isInstalledApp ? AppSourceType.installedApp : AppSourceType.webApp

  // Semantic variable for better code readability
  const isHistoryConversation = !!currentConversationId

  const appConfig = useMemo(() => {
    const config = appParams || {}

    return {
      ...config,
      file_upload: {
        ...(config as any).file_upload,
        fileUploadConfig: (config as any).system_parameters,
      },
      supportFeedback: true,
      opening_statement: currentConversationItem?.introduction || (config as any).opening_statement,
    } as ChatConfig
  }, [appParams, currentConversationItem?.introduction])
  const homepageFeaturesData = useMemo(() => {
    const fileUpload = appConfig.file_upload
    const fileUploadConfig = (fileUpload as FileUpload | undefined)?.fileUploadConfig
    const imageTransferMethods = (fileUpload?.allowed_file_upload_methods || [TransferMethod.local_file, TransferMethod.remote_url]) as TransferMethod[]
    const imageEnabled = !!fileUpload?.allowed_file_types?.includes(SupportUploadFileTypes.image)
    const fileEnabled = !!fileUpload?.allowed_file_types?.length

    return {
      moreLikeThis: appConfig.more_like_this || { enabled: false },
      opening: {
        enabled: !!appConfig.opening_statement,
        opening_statement: appConfig.opening_statement || '',
        suggested_questions: appConfig.suggested_questions || [],
      },
      moderation: appConfig.sensitive_word_avoidance || { enabled: false },
      speech2text: appConfig.speech_to_text || { enabled: false },
      text2speech: appConfig.text_to_speech || { enabled: false },
      file: {
        image: {
          detail: fileUpload?.image?.detail || Resolution.high,
          enabled: imageEnabled,
          number_limits: fileUpload?.number_limits || 3,
          transfer_methods: imageTransferMethods,
        },
        enabled: fileEnabled,
        allowed_file_types: fileUpload?.allowed_file_types || [],
        allowed_file_extensions: fileUpload?.allowed_file_extensions || [...FILE_EXTS[SupportUploadFileTypes.image], ...FILE_EXTS[SupportUploadFileTypes.video]].map(ext => `.${ext}`),
        allowed_file_upload_methods: imageTransferMethods,
        number_limits: fileUpload?.number_limits || 3,
        fileUploadConfig,
      } as FileUpload,
      suggested: appConfig.suggested_questions_after_answer || { enabled: false },
      citation: appConfig.retriever_resource || { enabled: false },
      annotationReply: appConfig.annotation_reply || { enabled: false },
    }
  }, [appConfig])
  const {
    chatList,
    handleSend,
    handleStop,
    handleSwitchSibling,
    isResponding: respondingState,
    suggestedQuestions,
  } = useChat(
    appConfig,
    {
      inputs: (currentConversationId ? currentConversationInputs : newConversationInputs) as any,
      inputsForm: inputsForms,
    },
    appPrevChatTree,
    taskId => stopChatMessageResponding('', taskId, appSourceType, appId),
    clearChatList,
    setClearChatList,
  )
  const inputsFormValue = currentConversationId ? currentConversationInputs : newConversationInputsRef?.current
  const inputDisabled = useMemo(() => {
    if (allInputsHidden)
      return false

    let hasEmptyInput = ''
    let fileIsUploading = false
    const requiredVars = inputsForms.filter(({ required, type }) => required && type !== InputVarType.checkbox)
    if (requiredVars.length) {
      requiredVars.forEach(({ variable, label, type }) => {
        if (hasEmptyInput)
          return

        if (fileIsUploading)
          return

        if (!inputsFormValue?.[variable])
          hasEmptyInput = label as string

        if ((type === InputVarType.singleFile || type === InputVarType.multiFiles) && inputsFormValue?.[variable]) {
          const files = inputsFormValue[variable]
          if (Array.isArray(files))
            fileIsUploading = files.find(item => item.transferMethod === TransferMethod.local_file && !item.uploadedId)
          else
            fileIsUploading = files.transferMethod === TransferMethod.local_file && !files.uploadedId
        }
      })
    }
    if (hasEmptyInput)
      return true

    if (fileIsUploading)
      return true

    if (chatList.some(item => item.isAnswer && item.humanInputFormDataList && item.humanInputFormDataList.length > 0))
      return true
    return false
  }, [allInputsHidden, inputsForms, chatList, inputsFormValue])

  useEffect(() => {
    if (currentChatInstanceRef.current)
      currentChatInstanceRef.current.handleStop = handleStop
  }, [currentChatInstanceRef, handleStop])

  useEffect(() => {
    setIsResponding(respondingState)
  }, [respondingState, setIsResponding])

  // Resume paused workflows when chat history is loaded
  useEffect(() => {
    if (!appPrevChatTree || appPrevChatTree.length === 0)
      return

    // Find the last answer item with workflow_run_id that needs resumption (DFS - find deepest first)
    let lastPausedNode: ChatItemInTree | undefined
    const findLastPausedWorkflow = (nodes: ChatItemInTree[]) => {
      nodes.forEach((node) => {
        // DFS: recurse to children first
        if (node.children && node.children.length > 0)
          findLastPausedWorkflow(node.children)

        // Track the last node with humanInputFormDataList
        if (node.isAnswer && node.workflow_run_id && node.humanInputFormDataList && node.humanInputFormDataList.length > 0)
          lastPausedNode = node
      })
    }

    findLastPausedWorkflow(appPrevChatTree)

    // Only resume the last paused workflow
    if (lastPausedNode) {
      handleSwitchSibling(
        lastPausedNode.id,
        {
          onGetConversationMessages: conversationId => fetchChatList(conversationId, appSourceType, appId),
          onGetSuggestedQuestions: responseItemId => fetchSuggestedQuestions(responseItemId, appSourceType, appId),
          onConversationComplete: currentConversationId ? undefined : handleNewConversationCompleted,
          onMessageCompleted,
          isPublicAPI: appSourceType === AppSourceType.webApp,
        },
      )
    }
  }, [appId, appPrevChatTree, appSourceType, currentConversationId, handleNewConversationCompleted, handleSwitchSibling, onMessageCompleted])

  const doSend: OnSend = useCallback((message, files, isRegenerate = false, parentAnswer: ChatItem | null = null) => {
    const data: any = {
      query: message,
      files,
      inputs: formatBooleanInputs(inputsForms, currentConversationId ? currentConversationInputs : newConversationInputs),
      conversation_id: currentConversationId,
      parent_message_id: (isRegenerate ? parentAnswer?.id : getLastAnswer(chatList)?.id) || null,
    }

    handleSend(
      getUrl('chat-messages', appSourceType, appId || ''),
      data,
      {
        onGetConversationMessages: conversationId => fetchChatList(conversationId, appSourceType, appId),
        onGetSuggestedQuestions: responseItemId => fetchSuggestedQuestions(responseItemId, appSourceType, appId),
        onConversationComplete: isHistoryConversation ? undefined : handleNewConversationCompleted,
        onMessageCompleted,
        isPublicAPI: appSourceType === AppSourceType.webApp,
      },
    )
  }, [inputsForms, currentConversationId, currentConversationInputs, newConversationInputs, chatList, handleSend, appSourceType, appId, isHistoryConversation, handleNewConversationCompleted, onMessageCompleted])

  const doRegenerate = useCallback((chatItem: ChatItem, editedQuestion?: { message: string, files?: FileEntity[] }) => {
    const question = editedQuestion ? chatItem : chatList.find(item => item.id === chatItem.parentMessageId)!
    const parentAnswer = chatList.find(item => item.id === question.parentMessageId)
    doSend(editedQuestion ? editedQuestion.message : question.content, editedQuestion ? editedQuestion.files : question.message_files, true, isValidGeneratedAnswer(parentAnswer) ? parentAnswer : null)
  }, [chatList, doSend])

  const doSwitchSibling = useCallback((siblingMessageId: string) => {
    handleSwitchSibling(siblingMessageId, {
      onGetConversationMessages: conversationId => fetchChatList(conversationId, appSourceType, appId),
      onGetSuggestedQuestions: responseItemId => fetchSuggestedQuestions(responseItemId, appSourceType, appId),
      onConversationComplete: currentConversationId ? undefined : handleNewConversationCompleted,
      onMessageCompleted,
      isPublicAPI: appSourceType === AppSourceType.webApp,
    })
  }, [handleSwitchSibling, currentConversationId, handleNewConversationCompleted, appSourceType, appId, onMessageCompleted])

  const messageList = useMemo(() => {
    if (currentConversationId || chatList.length > 1)
      return chatList
    // Without messages we are in the welcome screen, so hide the opening statement from chatlist
    return chatList.filter(item => !item.isOpeningStatement)
  }, [chatList, currentConversationId])

  const showHomepage = useMemo(() => {
    if (currentConversationId || respondingState)
      return false
    if (!allInputsHidden && inputsForms.length > 0)
      return false
    return messageList.length === 0
  }, [allInputsHidden, currentConversationId, inputsForms.length, messageList.length, respondingState])

  const handleSubmitHumanInputForm = useCallback(async (formToken: string, formData: any) => {
    if (isInstalledApp)
      await submitHumanInputFormService(formToken, formData)
    else
      await submitHumanInputForm(formToken, formData)
  }, [isInstalledApp])

  const [collapsed, setCollapsed] = useState(!!currentConversationId)
  const questionIcon = useMemo(() => {
    if (initUserVariables?.avatar_url) {
      return (
        <Avatar
          avatar={initUserVariables.avatar_url}
          name={initUserVariables.name || 'user'}
          size="xl"
        />
      )
    }

    if (appData?.site.default_user_avatar_url) {
      return (
        <Avatar
          avatar={appData.site.default_user_avatar_url}
          name={initUserVariables?.name || 'user'}
          size="xl"
        />
      )
    }

    return undefined
  }, [appData?.site.default_user_avatar_url, initUserVariables?.avatar_url, initUserVariables?.name])

  const chatNode = useMemo(() => {
    if (allInputsHidden || !inputsForms.length)
      return null
    if (isMobile) {
      if (!currentConversationId)
        return <InputsForm collapsed={collapsed} setCollapsed={setCollapsed} />
      return null
    }
    else {
      return <InputsForm collapsed={collapsed} setCollapsed={setCollapsed} />
    }
  }, [
    inputsForms.length,
    isMobile,
    currentConversationId,
    collapsed,
    allInputsHidden,
  ])

  const welcome = useMemo(() => {
    const welcomeMessage = chatList.find(item => item.isOpeningStatement)
    if (showHomepage) {
      const homepageDescription = appData?.site.description || ''
      const homepageTitle = appData?.site.title || '构界Agent'
      const quickActions = [
        '热门生成',
        '商品链接智能成片',
        '商品营销短视频',
        '海外商品介绍视频',
      ]

      return (
        <div className="px-4 py-4 md:px-6 md:py-6">
          <div className="relative mx-auto min-h-[calc(100vh-160px)] w-full max-w-[1480px] overflow-hidden rounded-[34px] border border-white/70 bg-[linear-gradient(135deg,#ffffff_0%,#f8faff_48%,#eef2ff_100%)] shadow-[0_28px_80px_rgba(99,102,241,0.12)]">
            <div className="inset-0 pointer-events-none absolute bg-[radial-gradient(circle_at_18%_12%,rgba(255,255,255,0.98),rgba(255,255,255,0.72)_34%,transparent_54%),radial-gradient(circle_at_82%_10%,rgba(196,181,253,0.22),transparent_28%),radial-gradient(circle_at_50%_100%,rgba(191,219,254,0.16),transparent_32%)]" />
            <div className="pointer-events-none absolute inset-x-5 inset-y-5 rounded-[28px] border border-[#e5e7f3] shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]" />

            <div className="relative flex min-h-[calc(100vh-160px)] flex-col px-7 pt-6 pb-7 md:px-10 md:pt-7 md:pb-10">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4 text-[#344054]">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[#e4e7ec] bg-white shadow-[0_8px_20px_rgba(99,102,241,0.08)]">
                    <AppIcon
                      size="large"
                      iconType={appData?.site.icon_type}
                      icon={appData?.site.icon}
                      background={appData?.site.icon_background}
                      imageUrl={appData?.site.icon_url}
                    />
                  </div>
                  <div className="text-[18px] font-semibold">{homepageTitle}</div>
                </div>
              </div>

              <div className="flex flex-1 flex-col items-center justify-center pt-8 text-center md:pt-10">
                <div className="max-w-[860px]">
                  <h1 className="text-[44px] leading-[1.12] font-black tracking-[-0.03em] text-[#111827] md:text-[64px]">
                    Hi, 欢迎使用
                    {' '}
                    <span className="bg-[linear-gradient(90deg,#4f6cf7_0%,#8b5cf6_58%,#c084fc_100%)] bg-clip-text text-transparent">
                      {homepageTitle}
                    </span>
                  </h1>
                  <div className="mt-6 text-[14px] tracking-[0.62em] text-[#667085] md:text-[16px]">
                    让 好 内 容 快 人 一 步
                  </div>
                  {!!homepageDescription && (
                    <div className="mx-auto mt-5 max-w-[620px] text-sm leading-6 text-[#667085]">
                      <Markdown className="!text-[#667085]" content={homepageDescription} mode="static" />
                    </div>
                  )}
                </div>

                <div className="mt-10 w-full max-w-[860px] px-4 md:px-8">
                  <div className="rounded-[34px] bg-[linear-gradient(135deg,#5f82f7_0%,#6ea7ff_34%,#b56cff_100%)] p-[4px] shadow-[0_24px_60px_rgba(99,102,241,0.2)]">
                    <FeaturesProvider features={homepageFeaturesData}>
                      <div className="overflow-hidden rounded-[30px] bg-[linear-gradient(180deg,rgba(255,255,255,0.8),rgba(255,255,255,0.98))]">
                        <div className="bg-white/88 px-5 pt-5 pb-4 md:px-6 md:pt-6 md:pb-5">
                          <ChatInputArea
                            botName={appData?.site.title}
                            placeholder="请输入您想要创作的内容"
                            appearance="homepage"
                            showFeatureBar={false}
                            showFileUpload
                            featureBarDisabled={respondingState || inputDisabled}
                            visionConfig={appConfig.file_upload}
                            speechToTextConfig={appConfig.speech_to_text}
                            onSend={(message, files) => doSend(message, files)}
                            inputs={(currentConversationId ? currentConversationInputs : newConversationInputs) as Record<string, unknown>}
                            inputsForm={inputsForms}
                            isResponding={respondingState}
                            disabled={inputDisabled}
                            hideSpeechButton
                            extraActions={(
                              <>
                                <button type="button" className="inline-flex h-11 items-center gap-2 rounded-[16px] border border-[#d9def1] bg-white px-5 text-[15px] font-medium text-[#475467] shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] transition hover:border-[#c7d2fe] hover:bg-[#f8faff]">
                                  <span className="i-ri-global-line h-[18px] w-[18px] text-[#667085]" />
                                  <span>抖音商品URL/ID</span>
                                </button>
                              </>
                            )}
                          />
                        </div>

                        <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-3 px-5 pt-2 pb-6 text-[14px] text-[#667085] md:px-6 md:pb-7 md:text-[15px]">
                          {quickActions.map((item, index) => (
                            <div key={item} className="flex items-center gap-5">
                              <button type="button" className="transition hover:text-[#4f46e5]">{item}</button>
                              {index < quickActions.length - 1 && <span className="hidden text-[#c0c6d9] md:inline">|</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    </FeaturesProvider>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )
    }

    if (respondingState)
      return null
    if (currentConversationId)
      return null
    if (!welcomeMessage)
      return null
    if (!collapsed && inputsForms.length > 0 && !allInputsHidden)
      return null
    if (welcomeMessage.suggestedQuestions && welcomeMessage.suggestedQuestions?.length > 0) {
      return (
        <div className="flex min-h-[50vh] items-center justify-center px-4 py-12">
          <div className="flex max-w-[720px] grow gap-4">
            <AppIcon
              size="xl"
              iconType={appData?.site.icon_type}
              icon={appData?.site.icon}
              background={appData?.site.icon_background}
              imageUrl={appData?.site.icon_url}
            />
            <div className="w-0 grow">
              <div className="grow rounded-2xl bg-chat-bubble-bg px-4 py-3 body-lg-regular text-text-primary">
                <Markdown content={welcomeMessage.content} mode="static" />
                <SuggestedQuestions item={welcomeMessage} />
              </div>
            </div>
          </div>
        </div>
      )
    }
    return (
      <div className={cn('flex min-h-[50vh] flex-col items-center justify-center gap-3 py-12')}>
        <AppIcon
          size="xl"
          iconType={appData?.site.icon_type}
          icon={appData?.site.icon}
          background={appData?.site.icon_background}
          imageUrl={appData?.site.icon_url}
        />
        <div className="max-w-[768px] px-4">
          <Markdown className="!body-2xl-regular !text-text-tertiary" content={welcomeMessage.content} mode="static" />
        </div>
      </div>
    )
  }, [
    appData?.site.description,
    appData?.site.title,
    appData?.site.icon,
    appData?.site.icon_background,
    appData?.site.icon_type,
    appData?.site.icon_url,
    chatList,
    collapsed,
    currentConversationId,
    currentConversationInputs,
    doSend,
    appConfig.file_upload,
    appConfig.speech_to_text,
    homepageFeaturesData,
    inputsForms,
    inputDisabled,
    newConversationInputs,
    respondingState,
    allInputsHidden,
    showHomepage,
  ])

  const answerIcon = (appData?.site && appData.site.use_icon_as_answer_icon)
    ? (
        <AnswerIcon
          iconType={appData.site.icon_type}
          icon={appData.site.icon}
          background={appData.site.icon_background}
          imageUrl={appData.site.icon_url}
        />
      )
    : null
  const footerNote = <span>{t('chat.aiGeneratedDisclaimer', { ns: 'share' })}</span>

  return (
    <div
      className={cn(
        'h-full overflow-hidden',
        !appData?.site.chat_page_background_color && 'bg-chatbot-bg',
      )}
      style={appData?.site.chat_page_background_color ? { backgroundColor: appData.site.chat_page_background_color } : undefined}
    >
      <Chat
        appData={appData ?? undefined}
        config={appConfig}
        chatList={messageList}
        isResponding={respondingState}
        chatContainerInnerClassName={`mx-auto pt-6 w-full max-w-[768px] ${isMobile && 'px-4'}`}
        chatFooterClassName="pb-4"
        chatFooterInnerClassName={`mx-auto w-full max-w-[768px] ${isMobile ? 'px-2' : 'px-4'}`}
        onSend={doSend}
        inputs={currentConversationId ? currentConversationInputs as any : newConversationInputs}
        inputsForm={inputsForms}
        onRegenerate={doRegenerate}
        onStopResponding={handleStop}
        onHumanInputFormSubmit={handleSubmitHumanInputForm}
        chatNode={(
          <>
            {chatNode}
            {welcome}
          </>
        )}
        allToolIcons={appMeta?.tool_icons || {}}
        onFeedback={handleFeedback}
        suggestedQuestions={suggestedQuestions}
        answerIcon={answerIcon}
        hideProcessDetail
        noChatInput={showHomepage}
        footerNote={footerNote}
        themeBuilder={themeBuilder}
        switchSibling={doSwitchSibling}
        inputDisabled={inputDisabled}
        sidebarCollapseState={sidebarCollapseState}
        questionIcon={questionIcon}
        hideAvatar
      />
    </div>
  )
}

export default ChatWrapper
