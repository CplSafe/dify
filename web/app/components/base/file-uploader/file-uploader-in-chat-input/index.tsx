import type { FileUpload } from '@/app/components/base/features/types'
import {
  memo,
  useCallback,
} from 'react'
import ActionButton from '@/app/components/base/action-button'
import { TransferMethod } from '@/types/app'
import { cn } from '@/utils/classnames'
import FileFromLinkOrLocal from '../file-from-link-or-local'

type FileUploaderInChatInputProps = {
  fileConfig: FileUpload
  readonly?: boolean
  triggerClassName?: string
  triggerIconClassName?: string
  triggerLabel?: string
}
const FileUploaderInChatInput = ({
  fileConfig,
  readonly,
  triggerClassName,
  triggerIconClassName,
  triggerLabel,
}: FileUploaderInChatInputProps) => {
  const renderTrigger = useCallback((open: boolean) => {
    return (
      <ActionButton
        size="l"
        className={cn(open && 'bg-state-base-hover', triggerClassName)}
        disabled={readonly}
      >
        <span className={cn('i-ri-attachment-line h-5 w-5', triggerIconClassName)} />
        {triggerLabel && <span className="ml-2">{triggerLabel}</span>}
      </ActionButton>
    )
  }, [readonly, triggerClassName, triggerIconClassName, triggerLabel])

  if (readonly)
    return renderTrigger(false)

  return (
    <FileFromLinkOrLocal
      trigger={renderTrigger}
      fileConfig={fileConfig}
      showFromLocal={fileConfig?.allowed_file_upload_methods?.includes(TransferMethod.local_file)}
      showFromLink={fileConfig?.allowed_file_upload_methods?.includes(TransferMethod.remote_url)}
    />
  )
}

export default memo(FileUploaderInChatInput)
