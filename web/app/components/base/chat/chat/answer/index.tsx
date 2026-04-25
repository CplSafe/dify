import type { FC, ReactNode } from 'react'
import type { ChatConfig, ChatItem } from '../../types'
import type { RerunController } from './rerun-context'
import type { AppData } from '@/models/share'
import {
  memo,
  startTransition,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { useTranslation } from 'react-i18next'
import { EditTitle } from '@/app/components/app/annotation/edit-annotation-modal/edit-item'
import AnswerIcon from '@/app/components/base/answer-icon'
import Citation from '@/app/components/base/chat/chat/citation'
import LoadingAnim from '@/app/components/base/chat/chat/loading-anim'
import DisclaimerText from '@/app/components/base/disclaimer-text'
import { FileList } from '@/app/components/base/file-uploader'
import { creatorMarkdownComponents as CREATOR_MD_COMPONENTS } from '@/app/components/creator/creator-markdown-components'
import {
  BlockEnum,
  WorkflowRunningStatus,
} from '@/app/components/workflow/types'
import { usePathname } from '@/next/navigation'
import { cn } from '@/utils/classnames'
import ContentSwitch from '../content-switch'
import { useChatContext } from '../context'
import AgentContent from './agent-content'
import BasicContent from './basic-content'
import HumanInputFilledFormList from './human-input-filled-form-list'
import HumanInputFormList from './human-input-form-list'
import More from './more'
import Operation from './operation'
import { RerunContext } from './rerun-context'
import SuggestedQuestions from './suggested-questions'
import WorkflowProcessItem from './workflow-process'

type AnswerProps = {
  item: ChatItem
  question: string
  index: number
  config?: ChatConfig
  answerIcon?: ReactNode
  responding?: boolean
  showPromptLog?: boolean
  chatAnswerContainerInner?: string
  hideProcessDetail?: boolean
  appData?: AppData
  noChatInput?: boolean
  switchSibling?: (siblingMessageId: string) => void
  hideAvatar?: boolean
  onHumanInputFormSubmit?: (formToken: string, formData: any) => Promise<void>
  // True when this is the last assistant message — only the last one
  // should expose rerun affordances so we don't fork the conversation tree.
  isLatestAnswer?: boolean
  // Surface that wires up node-level rerun (only the chatflow debug surface today).
  rerunController?: RerunController
}
const Answer: FC<AnswerProps> = ({
  item,
  question,
  index,
  config,
  answerIcon,
  responding,
  showPromptLog,
  chatAnswerContainerInner,
  hideProcessDetail,
  appData,
  noChatInput,
  switchSibling,
  hideAvatar,
  onHumanInputFormSubmit,
  isLatestAnswer = false,
  rerunController,
}) => {
  const { t } = useTranslation()
  const pathname = usePathname()
  const isCreatorMode = pathname?.startsWith('/creator')
  const creatorComponents = isCreatorMode ? CREATOR_MD_COMPONENTS : undefined
  const {
    content,
    citation,
    agent_thoughts,
    more,
    annotation,
    workflowProcess,
    allFiles,
    message_files,
    humanInputFormDataList,
    humanInputFilledFormDataList,
  } = item
  const hasAgentThoughts = !!agent_thoughts?.length
  const hasHumanInputs
    = !!humanInputFormDataList?.length || !!humanInputFilledFormDataList?.length
  const answerDisclaimer = appData?.site.show_answer_disclaimer
    ? appData?.site.custom_disclaimer
    : ''
  const appTitle = appData?.site.title || 'AI'
  const isWorkflowFinished
    = !workflowProcess
      || [
        WorkflowRunningStatus.Succeeded,
        WorkflowRunningStatus.Failed,
        WorkflowRunningStatus.Stopped,
      ].includes(workflowProcess.status as WorkflowRunningStatus)
  const shouldShowAnswerDisclaimer
    = !responding && !!answerDisclaimer && isWorkflowFinished
  const [_loadingStage, setLoadingStage] = useState<'analyzing' | 'retrieving'>(
    'analyzing',
  )
  const contentIsEmpty = typeof content === 'string' && content.trim() === ''
  const humanInputActionTexts
    = humanInputFilledFormDataList
      ?.map(formData => ({
        nodeId: formData.node_id,
        actionText: formData.action_text,
      }))
      .filter(item => item.actionText) || []
  const hasSubmittedHumanInput = !!humanInputFilledFormDataList?.length
  const hasRunningLoopNode = !!workflowProcess?.tracing?.some(
    node =>
      node.node_type === BlockEnum.Loop
      && node.status === WorkflowRunningStatus.Running,
  )
  const shouldShowPostHumanInputLoading
    = hasSubmittedHumanInput
      && contentIsEmpty
      && !hasAgentThoughts
      && !allFiles?.length
      && !message_files?.length

  const [containerWidth, setContainerWidth] = useState(0)
  const [contentWidth, setContentWidth] = useState(0)
  const [humanInputFormContainerWidth, setHumanInputFormContainerWidth]
    = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const humanInputFormContainerRef = useRef<HTMLDivElement>(null)

  const { getHumanInputNodeData } = useChatContext()

  const getContainerWidth = () => {
    if (containerRef.current)
      setContainerWidth(containerRef.current?.clientWidth + 16)
  }
  useEffect(() => {
    const frameId = window.requestAnimationFrame(getContainerWidth)
    return () => {
      window.cancelAnimationFrame(frameId)
    }
  }, [])

  const getContentWidth = () => {
    if (contentRef.current)
      setContentWidth(contentRef.current?.clientWidth)
  }

  useEffect(() => {
    if (!responding) {
      const frameId = window.requestAnimationFrame(getContentWidth)
      return () => {
        window.cancelAnimationFrame(frameId)
      }
    }
  }, [responding])

  useEffect(() => {
    if (!responding || !contentIsEmpty || hasAgentThoughts) {
      startTransition(() => {
        setLoadingStage('analyzing')
      })
      return
    }

    startTransition(() => {
      setLoadingStage('analyzing')
    })
    const timer = window.setTimeout(() => {
      startTransition(() => {
        setLoadingStage('retrieving')
      })
    }, 1200)

    return () => {
      window.clearTimeout(timer)
    }
  }, [contentIsEmpty, hasAgentThoughts, responding])

  const getHumanInputFormContainerWidth = () => {
    if (humanInputFormContainerRef.current) {
      setHumanInputFormContainerWidth(
        humanInputFormContainerRef.current?.clientWidth,
      )
    }
  }

  useEffect(() => {
    if (hasHumanInputs) {
      const frameId = window.requestAnimationFrame(
        getHumanInputFormContainerWidth,
      )
      return () => {
        window.cancelAnimationFrame(frameId)
      }
    }
  }, [hasHumanInputs])

  // Recalculate contentWidth when content changes (e.g., SVG preview/source toggle)
  useEffect(() => {
    if (!containerRef.current)
      return
    const resizeObserver = new ResizeObserver(() => {
      getContentWidth()
      getHumanInputFormContainerWidth()
    })
    resizeObserver.observe(containerRef.current)
    return () => {
      resizeObserver.disconnect()
    }
  }, [])

  const handleSwitchSibling = useCallback(
    (direction: 'prev' | 'next') => {
      if (direction === 'prev') {
        if (item.prevSibling)
          switchSibling?.(item.prevSibling)
      }
      else {
        if (item.nextSibling)
          switchSibling?.(item.nextSibling)
      }
    },
    [switchSibling, item.prevSibling, item.nextSibling],
  )

  const loadingText = hasRunningLoopNode
    ? '视频生成中'
    : hasSubmittedHumanInput
      ? `${appTitle} 正在继续生成视频`
      : `${appTitle} 正在分析需求`

  // Rerun is only enabled on the last assistant message AND once the workflow
  // has stopped streaming AND when the surface (chatflow debug) provided a
  // controller. Anything else means the affordance stays hidden.
  const effectiveRerunController
    = isLatestAnswer && !responding && isWorkflowFinished && rerunController
      ? rerunController
      : null

  const answerNode = (
    <div className="mb-2 flex last:mb-0">
      {!hideAvatar && (
        <div className="relative h-9 w-9 shrink-0 md:h-10 md:w-10">
          {answerIcon || <AnswerIcon />}
          {responding && (
            <div className="absolute left-[-3px] top-[-3px] flex h-4 w-4 items-center rounded-full border-[0.5px] border-divider-subtle bg-background-section-burn pl-[6px] shadow-xs">
              <LoadingAnim type="avatar" />
            </div>
          )}
        </div>
      )}
      <div
        className={cn(
          'group w-0 grow pb-3 md:pb-4',
          hideAvatar ? 'ml-0' : 'ml-2.5 md:ml-4',
        )}
        ref={containerRef}
        data-testid="chat-answer-container"
      >
        {/* Block 1: Workflow Process + Human Input Forms */}
        {hasHumanInputs && (
          <div
            className={cn(
              'group relative pr-1 md:pr-6',
              chatAnswerContainerInner,
            )}
            data-testid="chat-answer-container-humaninput"
          >
            <div
              ref={humanInputFormContainerRef}
              className={cn(
                'relative inline-block w-full max-w-full text-text-primary body-lg-regular',
                isCreatorMode
                  ? 'bg-transparent px-0 py-0 shadow-none'
                  : 'rounded-[28px] border border-components-panel-border-subtle bg-background-section px-4 py-4 shadow-lg md:px-5',
              )}
            >
              {!responding && contentIsEmpty && !hasAgentThoughts && (
                <Operation
                  hasWorkflowProcess={!!workflowProcess}
                  maxSize={containerWidth - humanInputFormContainerWidth - 4}
                  contentWidth={humanInputFormContainerWidth}
                  item={item}
                  question={question}
                  index={index}
                  showPromptLog={showPromptLog}
                  noChatInput={noChatInput}
                />
              )}
              {/** Render workflow process */}
              {workflowProcess && (
                <WorkflowProcessItem
                  data={workflowProcess}
                  item={item}
                  hideProcessDetail={hideProcessDetail}
                  readonly={
                    hideProcessDetail && appData
                      ? !appData.site.show_workflow_steps
                      : undefined
                  }
                />
              )}
              {humanInputFormDataList && humanInputFormDataList.length > 0 && (
                <HumanInputFormList
                  humanInputFormDataList={humanInputFormDataList}
                  onHumanInputFormSubmit={onHumanInputFormSubmit}
                  getHumanInputNodeData={getHumanInputNodeData}
                />
              )}
              {humanInputFilledFormDataList
                && humanInputFilledFormDataList.length > 0 && (
                <HumanInputFilledFormList
                  humanInputFilledFormDataList={humanInputFilledFormDataList}
                />
              )}
              {typeof item.siblingCount === 'number'
                && item.siblingCount > 1
                && !responding
                && contentIsEmpty
                && !hasAgentThoughts && (
                <ContentSwitch
                  count={item.siblingCount}
                  currentIndex={item.siblingIndex}
                  prevDisabled={!item.prevSibling}
                  nextDisabled={!item.nextSibling}
                  switchSibling={handleSwitchSibling}
                />
              )}
            </div>
          </div>
        )}

        {humanInputActionTexts.length > 0 && (
          <div className="mt-2">
            {humanInputActionTexts.map(item => (
              <div
                key={`${item.nodeId}-action`}
                className="mb-2 flex justify-end last:mb-0"
              >
                <div
                  className={cn(
                    'group relative flex max-w-full items-start overflow-x-hidden',
                    hideAvatar ? 'mr-0' : 'mr-4 pl-14',
                  )}
                >
                  <div
                    className="w-full rounded-2xl bg-background-gradient-bg-fill-chat-bubble-bg-3 px-4 py-3 text-sm text-text-primary"
                    data-testid="human-input-action-question"
                  >
                    {item.actionText}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Block 2: Response Content (when human inputs exist) */}
        {hasHumanInputs
          && (responding
            || !contentIsEmpty
            || hasAgentThoughts
            || shouldShowPostHumanInputLoading) && (
          <div
            className={cn(
              'group relative mt-3 pr-1 md:pr-6',
              chatAnswerContainerInner,
            )}
          >
            {!isCreatorMode && (
              <div className="absolute -top-3 left-8 h-4 w-0.5 bg-chat-answer-human-input-form-divider-bg" />
            )}
            <div
              ref={contentRef}
              className={cn(
                'relative inline-block w-full max-w-full text-text-primary body-lg-regular',
                isCreatorMode
                  ? 'bg-transparent px-0 py-2 shadow-none'
                  : 'rounded-[24px] border border-components-panel-border-subtle bg-background-default px-4 py-3 shadow-sm md:px-5 md:py-4',
              )}
            >
              {!responding && (
                <Operation
                  hasWorkflowProcess={!!workflowProcess}
                  maxSize={containerWidth - contentWidth - 4}
                  contentWidth={contentWidth}
                  item={item}
                  question={question}
                  index={index}
                  showPromptLog={showPromptLog}
                  noChatInput={noChatInput}
                />
              )}
              {((responding && contentIsEmpty && !hasAgentThoughts)
                || shouldShowPostHumanInputLoading) && (
                <div className="flex min-h-6 items-center gap-1.5 text-xs text-text-primary">
                  <span
                    aria-hidden
                    className="i-ri-loader-2-line h-3 w-3 shrink-0 animate-spin text-text-tertiary"
                  />
                  <span>{loadingText}</span>
                </div>
              )}
              {!contentIsEmpty && !hasAgentThoughts && (
                <BasicContent
                  item={item}
                  responding={responding}
                  customMarkdownComponents={creatorComponents}
                />
              )}
              {hasAgentThoughts && (
                <AgentContent
                  item={item}
                  responding={responding}
                  content={content}
                />
              )}
              {!!allFiles?.length && (
                <FileList
                  className="my-1"
                  files={allFiles}
                  showDeleteAction={false}
                  showDownloadAction
                  canPreview
                />
              )}
              {!!message_files?.length && (
                <FileList
                  className="my-1"
                  files={message_files}
                  showDeleteAction={false}
                  showDownloadAction
                  canPreview
                />
              )}
              {annotation?.id && annotation.authorName && (
                <EditTitle
                  className="mt-1"
                  title={t('editBy', {
                    ns: 'appAnnotation',
                    author: annotation.authorName,
                  })}
                />
              )}
              <SuggestedQuestions item={item} />
              {!!citation?.length && !responding && (
                <Citation
                  data={citation}
                  showHitInfo={config?.supportCitationHitInfo}
                />
              )}
              {shouldShowAnswerDisclaimer && (
                <DisclaimerText
                  className="mt-3 border-t border-divider-subtle pt-3 text-xs text-text-tertiary"
                  content={answerDisclaimer}
                />
              )}
              {typeof item.siblingCount === 'number'
                && item.siblingCount > 1 && (
                <ContentSwitch
                  count={item.siblingCount}
                  currentIndex={item.siblingIndex}
                  prevDisabled={!item.prevSibling}
                  nextDisabled={!item.nextSibling}
                  switchSibling={handleSwitchSibling}
                />
              )}
            </div>
          </div>
        )}

        {/* Original single block layout (when no human inputs) */}
        {!hasHumanInputs && (
          <div
            className={cn(
              'group relative pr-1 md:pr-10',
              chatAnswerContainerInner,
            )}
            data-testid="chat-answer-container-inner"
          >
            <div
              ref={contentRef}
              className={cn(
                'relative inline-block max-w-full text-text-primary body-lg-regular',
                isCreatorMode
                  ? 'w-full bg-transparent px-0 py-2'
                  : 'rounded-2xl bg-chat-bubble-bg px-3.5 py-2.5 md:px-4 md:py-3',
                workflowProcess && 'w-full',
              )}
            >
              {!responding && (
                <Operation
                  hasWorkflowProcess={!!workflowProcess}
                  maxSize={containerWidth - contentWidth - 4}
                  contentWidth={contentWidth}
                  item={item}
                  question={question}
                  index={index}
                  showPromptLog={showPromptLog}
                  noChatInput={noChatInput}
                />
              )}
              {/** Render workflow process */}
              {workflowProcess && (
                <WorkflowProcessItem
                  data={workflowProcess}
                  item={item}
                  hideProcessDetail={hideProcessDetail}
                  readonly={
                    hideProcessDetail && appData
                      ? !appData.site?.show_workflow_steps
                      : undefined
                  }
                />
              )}
              {responding && contentIsEmpty && !hasAgentThoughts && (
                <div className="flex min-h-6 items-center gap-1.5 text-xs text-text-primary">
                  <span
                    aria-hidden
                    className="i-ri-loader-2-line h-3 w-3 shrink-0 animate-spin text-text-tertiary"
                  />
                  <span>{loadingText}</span>
                </div>
              )}
              {!contentIsEmpty && !hasAgentThoughts && (
                <BasicContent
                  item={item}
                  responding={responding}
                  customMarkdownComponents={creatorComponents}
                />
              )}
              {hasAgentThoughts && (
                <AgentContent
                  item={item}
                  responding={responding}
                  content={content}
                />
              )}
              {!!allFiles?.length && (
                <FileList
                  className="my-1"
                  files={allFiles}
                  showDeleteAction={false}
                  showDownloadAction
                  canPreview
                />
              )}
              {!!message_files?.length && (
                <FileList
                  className="my-1"
                  files={message_files}
                  showDeleteAction={false}
                  showDownloadAction
                  canPreview
                />
              )}
              {annotation?.id && annotation.authorName && (
                <EditTitle
                  className="mt-1"
                  title={t('editBy', {
                    ns: 'appAnnotation',
                    author: annotation.authorName,
                  })}
                />
              )}
              <SuggestedQuestions item={item} />
              {!!citation?.length && !responding && (
                <Citation
                  data={citation}
                  showHitInfo={config?.supportCitationHitInfo}
                />
              )}
              {shouldShowAnswerDisclaimer && (
                <DisclaimerText
                  className="mt-3 border-t border-divider-subtle pt-3 text-xs text-text-tertiary"
                  content={answerDisclaimer}
                />
              )}
              {typeof item.siblingCount === 'number'
                && item.siblingCount > 1 && (
                <ContentSwitch
                  count={item.siblingCount}
                  currentIndex={item.siblingIndex}
                  prevDisabled={!item.prevSibling}
                  nextDisabled={!item.nextSibling}
                  switchSibling={handleSwitchSibling}
                />
              )}
            </div>
          </div>
        )}
        {!isCreatorMode && <More more={more} />}
      </div>
    </div>
  )

  if (!effectiveRerunController)
    return answerNode

  return (
    <RerunContext value={effectiveRerunController}>{answerNode}</RerunContext>
  )
}

export default memo(Answer)
