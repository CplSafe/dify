'use client'

import type { ChatItem } from '@/app/components/base/chat/types'
import type { AppData } from '@/models/share'
import { useMemo } from 'react'
import { Markdown } from '@/app/components/base/markdown'
import HumanInputFormList from '@/app/components/base/chat/chat/answer/human-input-form-list'
import HumanInputFilledFormList from '@/app/components/base/chat/chat/answer/human-input-filled-form-list'
import { cn } from '@/utils/classnames'

type CreatorTaskLayoutProps = {
  chatList: ChatItem[]
  activeHumanInputAnswer: ChatItem
  onSubmitHumanInput: (formToken: string, formData: any) => Promise<void>
  appData?: AppData | null
  getHumanInputNodeData?: (nodeID: string) => any
  isResponding?: boolean
}

export default function CreatorTaskLayout({
  chatList,
  activeHumanInputAnswer,
  onSubmitHumanInput,
  getHumanInputNodeData,
  isResponding,
}: CreatorTaskLayoutProps) {

  // Whether there are pending (unsubmitted) human input forms
  const hasPendingForms = !!(activeHumanInputAnswer.humanInputFormDataList && activeHumanInputAnswer.humanInputFormDataList.length > 0)
  // Whether there are already-submitted human input forms
  const hasFilledForms = !!(activeHumanInputAnswer.humanInputFilledFormDataList && activeHumanInputAnswer.humanInputFilledFormDataList.length > 0)
  // Workflow is still processing after form submission
  const isProcessingAfterSubmit = !hasPendingForms && (hasFilledForms || isResponding)

  // Extract user's initial request (first question in chatList)
  const initialQuestion = useMemo(() => {
    return chatList.find(item => !item.isAnswer && !item.isOpeningStatement)
  }, [chatList])

  // Extract AI's process description (content from the active answer, or previous answer if active is just a form)
  const aiProcessText = useMemo(() => {
    if (activeHumanInputAnswer.content) {
      return activeHumanInputAnswer.content
    }
    // If current answer has no content, try to find the previous answer's content
    const prevAnswer = [...chatList].reverse().find(item => item.isAnswer && item.id !== activeHumanInputAnswer.id)
    return prevAnswer?.content || 'AI 正在分析您的需求，并准备了以下内容请确认：'
  }, [activeHumanInputAnswer, chatList])

  return (
    <div className="flex h-full w-full bg-[#FBFBFF] overflow-hidden">
      {/* Left Area: Main Form Content */}
      <div className="flex-1 overflow-y-auto p-8 relative">
        <div className="absolute -left-[10%] -top-[10%] h-[50%] w-[50%] rounded-full bg-[#E0E9FF] opacity-40 blur-[120px] pointer-events-none" />
        <div className="absolute -right-[5%] bottom-[10%] h-[40%] w-[40%] rounded-full bg-[#F3E8FF] opacity-50 blur-[100px] pointer-events-none" />

        <div className="relative z-10 max-w-4xl mx-auto pb-20">
          <div className="mb-6 flex items-center gap-2 text-sm font-medium text-text-tertiary">
            <span className="i-ri-magic-line text-primary-600" />
            {isProcessingAfterSubmit
              ? '已确认内容，AI 正在生成最终结果，请稍候...'
              : '基于您的需求，AI 已生成以下可编辑内容，确认无误后进入下一步'}
          </div>

          {/* Pending (unsubmitted) forms — user can still edit and submit */}
          {hasPendingForms && (
            <HumanInputFormList
              humanInputFormDataList={activeHumanInputAnswer.humanInputFormDataList || []}
              onHumanInputFormSubmit={onSubmitHumanInput}
              getHumanInputNodeData={getHumanInputNodeData}
            />
          )}

          {/* Submitted (filled) forms — read-only view while workflow continues */}
          {hasFilledForms && (
            <HumanInputFilledFormList
              humanInputFilledFormDataList={activeHumanInputAnswer.humanInputFilledFormDataList || []}
            />
          )}

          {/* Processing indicator after forms are submitted */}
          {isProcessingAfterSubmit && (
            <div className="mt-8 flex flex-col items-center justify-center gap-4 rounded-2xl border border-primary-100 bg-white p-8 shadow-sm">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-50">
                <span className="i-ri-loader-4-line h-6 w-6 animate-spin text-primary-600" />
              </div>
              <div className="text-base font-medium text-text-primary">AI 正在生成内容</div>
              <div className="text-sm text-text-tertiary">
                已收到您确认的内容，正在根据需求生成最终结果...
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Area: Sidebar Timeline / Flow */}
      <div className="w-[360px] shrink-0 border-l border-[#E9E9EB] bg-[#F5F5F7] flex flex-col relative z-20">
        <div className="bg-gradient-to-r from-[#80A7FF] to-[#B98DFF] px-5 py-4 flex items-center justify-between text-white rounded-tl-2xl">
          <h2 className="font-bold text-base tracking-wide">创作流程</h2>
          <button className="h-6 w-6 rounded-full bg-white/20 flex items-center justify-center hover:bg-white/30 transition-colors">
            <span className="i-ri-close-line h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-6 space-y-6">
          {/* Step 1: User Input */}
          {initialQuestion && (
            <div className="space-y-3">
              <div className="text-sm font-semibold text-text-primary">1. 你的创作需求</div>
              <div className="rounded-xl bg-white p-4 shadow-sm border border-[#E9E9EB]">
                <div className="text-sm text-text-secondary leading-relaxed line-clamp-4">
                  {initialQuestion.content}
                </div>
                {initialQuestion.message_files && initialQuestion.message_files.length > 0 && (
                  <div className="mt-3 flex items-center gap-2 rounded-lg bg-[#F5F5F7] px-3 py-2 text-xs text-text-secondary">
                    <span className="i-ri-attachment-2 h-4 w-4 text-primary-600" />
                    <span className="truncate">已包含附件/链接</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Step 2: AI Process */}
          <div className="space-y-3 relative">
            {/* Connecting Line */}
            <div className="absolute -top-6 left-6 h-6 w-[2px] bg-primary-200" />
            <div className="flex items-center gap-2">
              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-primary-100 text-primary-600">
                <span className="i-ri-robot-2-line h-3 w-3" />
              </div>
              <div className="text-sm font-semibold text-primary-700">2. AI 分析与构思</div>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm border border-primary-100 ring-1 ring-primary-50">
              <div className="text-[13px] text-text-secondary leading-relaxed max-h-[200px] overflow-y-auto custom-scrollbar">
                <Markdown content={aiProcessText} mode="static" />
              </div>
            </div>
          </div>

          {/* Step 3: Current Action */}
          <div className="space-y-3 relative">
            {/* Connecting Line */}
            <div className="absolute -top-6 left-[1.125rem] h-6 w-[2px] border-l-2 border-dashed border-[#D1D1D6]" />
            <div className={cn(
              'text-sm font-semibold pl-8 relative',
              isProcessingAfterSubmit ? 'text-primary-700' : 'text-text-tertiary',
            )}>
              <div className={cn(
                'absolute left-[0.6rem] top-1 h-2 w-2 rounded-full border-2',
                isProcessingAfterSubmit
                  ? 'border-primary-500 bg-primary-100 animate-pulse'
                  : 'border-[#D1D1D6] bg-[#F5F5F7]',
              )} />
              3. {isProcessingAfterSubmit ? '正在生成最终结果...' : '确认并生成最终结果'}
            </div>

            <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm border border-[#E9E9EB] text-center relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-br from-[#80A7FF]/5 to-[#B98DFF]/5" />
              {isProcessingAfterSubmit
                ? (
                  <div className="relative z-10 flex flex-col items-center gap-2 py-2">
                    <span className="i-ri-loader-4-line h-5 w-5 animate-spin text-primary-600" />
                    <div className="text-sm font-medium text-primary-700">生成中...</div>
                  </div>
                )
                : (
                  <>
                    <button
                      className="relative z-10 w-full rounded-xl bg-gradient-to-r from-[#80A7FF] to-[#B98DFF] py-3 text-sm font-bold text-white shadow-md transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-50 disabled:grayscale"
                      disabled
                    >
                      生成内容
                    </button>
                    <div className="relative z-10 mt-3 text-xs text-text-tertiary">
                      <span className="i-ri-magic-line mr-1 inline-block align-middle" />
                      请在左侧确认内容后点击表单中的按钮继续
                    </div>
                  </>
                )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
