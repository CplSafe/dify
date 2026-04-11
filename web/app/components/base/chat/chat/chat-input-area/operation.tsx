import type { FC, ReactNode, Ref } from 'react'
import type { Theme } from '../../embedded-chatbot/theme/theme-context'
import type {
  EnableType,
} from '../../types'
import type { FileUpload } from '@/app/components/base/features/types'
import { noop } from 'es-toolkit/function'
import { memo } from 'react'
import ActionButton from '@/app/components/base/action-button'
import Button from '@/app/components/base/button'
import { FileUploaderInChatInput } from '@/app/components/base/file-uploader'
import { cn } from '@/utils/classnames'

type OperationProps = {
  readonly?: boolean
  fileConfig?: FileUpload
  speechToTextConfig?: EnableType
  onShowVoiceInput?: () => void
  onSend: () => void
  theme?: Theme | null
  appearance?: 'default' | 'homepage'
  extraActions?: ReactNode
  hideSpeechButton?: boolean
  ref?: Ref<HTMLDivElement>
}
const Operation: FC<OperationProps> = ({
  readonly,
  ref,
  fileConfig,
  speechToTextConfig,
  onShowVoiceInput,
  onSend,
  theme,
  appearance = 'default',
  extraActions,
  hideSpeechButton,
}) => {
  const isHomepage = appearance === 'homepage'

  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-end',
        isHomepage && 'w-full justify-between',
      )}
    >
      <div
        className={cn(
          'flex items-center pl-1',
          isHomepage && 'w-full justify-between pl-0',
        )}
        ref={ref}
      >
        <div className="flex flex-wrap items-center gap-2">
          {extraActions}
          {fileConfig?.enabled && (
            <FileUploaderInChatInput
              readonly={readonly}
              fileConfig={fileConfig}
              triggerLabel={isHomepage ? '上传' : undefined}
              triggerClassName={isHomepage ? 'h-11 rounded-[16px] border border-[#d9def1] bg-white px-5 text-[15px] font-medium text-[#475467] shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] transition hover:border-[#c7d2fe] hover:bg-[#f8faff]' : undefined}
              triggerIconClassName={isHomepage ? 'h-[18px] w-[18px] text-[#667085]' : undefined}
            />
          )}
          {
            speechToTextConfig?.enabled && !hideSpeechButton && (
              <ActionButton
                size="l"
                disabled={readonly}
                onClick={onShowVoiceInput}
                data-testid="voice-input-button"
                className={cn(isHomepage && 'h-11 rounded-[16px] border border-[#d9def1] bg-white px-4 text-[#667085] transition hover:border-[#c7d2fe] hover:bg-[#f8faff]')}
              >
                <span className="i-ri-mic-line h-5 w-5" />
              </ActionButton>
            )
          }
        </div>
        <Button
          className={cn(
            'ml-3 w-8 px-0',
            isHomepage && 'ml-4 h-14 w-14 rounded-full border-0 bg-[linear-gradient(135deg,#e9ddff_0%,#be8cff_42%,#6d7cff_100%)] px-0 text-white shadow-[0_16px_36px_rgba(129,140,248,0.38),inset_0_1px_0_rgba(255,255,255,0.55)] transition hover:translate-y-[-1px] hover:shadow-[0_20px_42px_rgba(129,140,248,0.46)]',
          )}
          variant="primary"
          onClick={readonly ? noop : onSend}
          data-testid="send-button"
          style={
            theme
              ? {
                  backgroundColor: theme.primaryColor,
                }
              : {}
          }
        >
          {isHomepage ? <span className="i-ri-sparkling-fill h-6 w-6" /> : <span className="i-ri-send-plane-2-fill h-4 w-4" />}
        </Button>
      </div>
    </div>
  )
}
Operation.displayName = 'Operation'

export default memo(Operation)
