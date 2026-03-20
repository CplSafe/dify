import type { FileEntity } from '../../file-uploader/types'
import type {
  ChatConfig,
  ChatItem,
  ChatItemInTree,
  OnSend,
} from '../types'
import type { FileUpload } from '@/app/components/base/features/types'
import { useCallback, useEffect, useMemo, useState } from 'react'
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

const ChatWrapper = () => {
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
          onGetSuggestedQuestions: responseItemId => fetchSuggestedQuestions(responseItemId, appSourceType, appId),
          onConversationComplete: currentConversationId ? undefined : handleNewConversationCompleted,
          isPublicAPI: appSourceType === AppSourceType.webApp,
        },
      )
    }
  }, [appId, appPrevChatTree, appSourceType, currentConversationId, handleNewConversationCompleted, handleSwitchSibling])

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
        onGetSuggestedQuestions: responseItemId => fetchSuggestedQuestions(responseItemId, appSourceType, appId),
        onConversationComplete: isHistoryConversation ? undefined : handleNewConversationCompleted,
        isPublicAPI: appSourceType === AppSourceType.webApp,
      },
    )
  }, [inputsForms, currentConversationId, currentConversationInputs, newConversationInputs, chatList, handleSend, appSourceType, appId, isHistoryConversation, handleNewConversationCompleted])

  const doRegenerate = useCallback((chatItem: ChatItem, editedQuestion?: { message: string, files?: FileEntity[] }) => {
    const question = editedQuestion ? chatItem : chatList.find(item => item.id === chatItem.parentMessageId)!
    const parentAnswer = chatList.find(item => item.id === question.parentMessageId)
    doSend(editedQuestion ? editedQuestion.message : question.content, editedQuestion ? editedQuestion.files : question.message_files, true, isValidGeneratedAnswer(parentAnswer) ? parentAnswer : null)
  }, [chatList, doSend])

  const doSwitchSibling = useCallback((siblingMessageId: string) => {
    handleSwitchSibling(siblingMessageId, {
      onGetSuggestedQuestions: responseItemId => fetchSuggestedQuestions(responseItemId, appSourceType, appId),
      onConversationComplete: currentConversationId ? undefined : handleNewConversationCompleted,
      isPublicAPI: appSourceType === AppSourceType.webApp,
    })
  }, [handleSwitchSibling, currentConversationId, handleNewConversationCompleted, appSourceType, appId])

  const messageList = useMemo(() => {
    if (currentConversationId || chatList.length > 1)
      return chatList
    // Without messages we are in the welcome screen, so hide the opening statement from chatlist
    return chatList.filter(item => !item.isOpeningStatement)
  }, [chatList, currentConversationId])

  const showHomepage = useMemo(() => {
    if (!appData?.site.enable_homepage)
      return false
    if (currentConversationId || respondingState)
      return false
    if (!allInputsHidden && inputsForms.length > 0)
      return false
    return messageList.length === 0
  }, [allInputsHidden, appData?.site.enable_homepage, currentConversationId, inputsForms.length, messageList.length, respondingState])

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
      const homepageDescription = appData?.site.description || appConfig.opening_statement || ''
      const homepageTitle = '益阳赫山'

      return (
        <div className="px-4 py-6 md:px-6 md:py-8">
          <div className="relative mx-auto min-h-[calc(100vh-180px)] w-full max-w-[760px] overflow-hidden rounded-[36px] border border-white/60 bg-[linear-gradient(145deg,#fdf2f8_0%,#fff7ed_42%,#f8fafc_100%)] shadow-[0_30px_80px_rgba(249,115,22,0.14)]">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_14%,rgba(251,113,133,0.28),transparent_34%),radial-gradient(circle_at_80%_22%,rgba(253,186,116,0.26),transparent_30%),radial-gradient(circle_at_52%_72%,rgba(255,255,255,0.72),transparent_44%)]" />
            <div className="absolute -left-16 top-28 h-56 w-56 rounded-full bg-[rgba(255,255,255,0.32)] blur-3xl" />
            <div className="absolute -right-8 bottom-40 h-48 w-48 rounded-full bg-[rgba(255,255,255,0.26)] blur-3xl" />

            <div className="relative flex min-h-[calc(100vh-180px)] flex-col px-5 pb-8 pt-5 md:px-8 md:pb-10 md:pt-7">
              <div className="inline-flex w-fit items-center gap-2 rounded-full bg-[rgba(255,255,255,0.88)] px-4 py-2 text-[15px] font-semibold text-[#f97316] shadow-[0_10px_30px_rgba(255,255,255,0.55)]">
                <div className="i-ri-map-pin-2-fill h-4 w-4" />
                <span>{homepageTitle}</span>
              </div>

              <div className="flex flex-1 flex-col items-center justify-center py-10 text-center md:py-14">
                <div className="pointer-events-none absolute left-[18%] top-[28%] h-36 w-36 rounded-full border-[6px] border-[#fb7185]/45" />
                <div className="pointer-events-none absolute right-[16%] top-[34%] h-28 w-28 rounded-full border-[5px] border-[#fdba74]/40" />
                <div className="pointer-events-none absolute left-[22%] top-[48%] h-3 w-3 rounded-full bg-[#fb7185]" />
                <div className="pointer-events-none absolute right-[24%] top-[46%] h-4 w-4 rounded-full bg-[#fdba74]" />

                <div className="text-[40px] font-black italic leading-none tracking-[0.08em] text-[#f97316] drop-shadow-[0_10px_22px_rgba(249,115,22,0.18)] md:text-[58px]">
                  赫山
                </div>
                <div className="mt-2 text-[68px] font-black italic leading-none tracking-[0.04em] text-[#ef4444] drop-shadow-[0_18px_30px_rgba(239,68,68,0.18)] md:text-[108px]">
                  百事通
                </div>

                <div className="relative mt-8 flex w-full max-w-[430px] justify-center md:mt-10">
                  <div className="absolute inset-x-12 bottom-4 h-12 rounded-full bg-[radial-gradient(circle,rgba(249,115,22,0.2),transparent_68%)] blur-2xl" />
                  <div className="absolute inset-x-10 top-6 h-[72%] rounded-[36px] bg-[radial-gradient(circle_at_50%_20%,rgba(255,255,255,0.55),rgba(255,255,255,0.08)_56%,transparent_78%)] blur-xl" />
                  <div className="absolute left-1/2 top-[18%] h-[64%] w-[58%] -translate-x-1/2 rounded-[42px] bg-[linear-gradient(180deg,rgba(255,255,255,0.18),rgba(255,255,255,0.04))] shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] backdrop-blur-[1px]" />
                  <img
                    src="/logo/webapphome-transparent.png"
                    alt="赫事通首页形象"
                    className="relative z-10 w-full max-w-[330px] select-none object-contain drop-shadow-[0_40px_42px_rgba(124,45,18,0.2)] saturate-[1.12] contrast-[1.04] brightness-[1.01] md:max-w-[372px]"
                  />
                  <div className="pointer-events-none absolute left-1/2 top-[12%] z-20 h-[18%] w-[34%] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.3),transparent_72%)] blur-2xl" />
                </div>

                {!!homepageDescription && (
                  <div className="mt-8 max-w-[520px] text-sm leading-6 text-[#7c2d12]/70 md:mt-10">
                    <Markdown className="!text-[#7c2d12]/70" content={homepageDescription} />
                  </div>
                )}
              </div>

              <div className="mx-auto w-full max-w-[640px]">
                <div className="rounded-[28px] bg-[rgba(255,255,255,0.42)] p-0 shadow-[0_22px_40px_rgba(249,115,22,0.12)] backdrop-blur-sm">
                  <FeaturesProvider features={homepageFeaturesData}>
                    <div className="[&>div:first-child]:rounded-[24px] [&>div:first-child]:border-0 [&>div:first-child]:bg-white [&>div:first-child]:shadow-[0_12px_28px_rgba(124,45,18,0.12)] [&>div:first-child>div:first-child]:px-[14px] [&>div:first-child>div:first-child]:pt-[12px] [&_textarea]:px-0 [&_textarea]:text-[18px] [&_textarea]:text-[#7c2d12] [&_textarea]:placeholder:text-[#9ca3af]">
                      <ChatInputArea
                        botName={appData?.site.title}
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
                      />
                    </div>
                  </FeaturesProvider>
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
              <div className="grow rounded-2xl bg-chat-bubble-bg px-4 py-3 text-text-primary body-lg-regular">
                <Markdown content={welcomeMessage.content} />
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
          <Markdown className="!text-text-tertiary !body-2xl-regular" content={welcomeMessage.content} />
        </div>
      </div>
    )
  }, [
    appConfig.opening_statement,
    appData?.site.description,
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
    appData?.site.title,
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

  return (
    <div
      className="h-full overflow-hidden bg-chatbot-bg"
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
        themeBuilder={themeBuilder}
        switchSibling={doSwitchSibling}
        inputDisabled={inputDisabled}
        sidebarCollapseState={sidebarCollapseState}
        questionIcon={questionIcon}
      />
    </div>
  )
}

export default ChatWrapper
