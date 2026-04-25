'use client'

import type { FC, KeyboardEvent, ReactNode } from 'react'
import type { FileEntity } from '@/app/components/base/file-uploader/types'
import { RiAttachment2, RiSendPlane2Fill } from '@remixicon/react'
import { useCallback, useMemo, useRef, useState } from 'react'
import {
  FileFromLinkOrLocal,
  FileListInChatInput,
} from '@/app/components/base/file-uploader'
import {
  FileContextProvider,
  useStore as useFileStore,
} from '@/app/components/base/file-uploader/store'
import { TransferMethod } from '@/types/app'
import { cn } from '@/utils/classnames'

export type RuntimeInputSubmitPayload = {
  text: string
  files: FileEntity[]
}

type RuntimeInputProps = {
  // chatflow file_upload feature config — passed straight through to
  // FileFromLinkOrLocal so allowed types / max size match the app's
  // own settings. Optional so CR4-only mounts still render.
  fileConfig?: unknown
  onSubmit: (payload: RuntimeInputSubmitPayload) => void
  disabled?: boolean
  placeholder?: string
  // Optional slot above the textarea for the start-node user_input_form.
  // Page passes the rendered <RuntimeStartVars /> so this component
  // doesn't need to know about chatflow internals.
  startSlot?: ReactNode
}

// Minimal slash-menu placeholder. Real entries (素材/提示词/图/视频/音频)
// land in a follow-up; this just proves the keystroke detection +
// popover positioning so the integration cost later is zero.
type SlashEntry = { id: string, label: string, hint: string }
const _SLASH_PLACEHOLDER: SlashEntry[] = [
  { id: '__placeholder_at__', label: '@ 引用', hint: '即将支持引用素材库内容' },
  {
    id: '__placeholder_slash__',
    label: '/ 命令',
    hint: '即将支持插入提示词模板',
  },
]

const RuntimeInputInner: FC<RuntimeInputProps> = ({
  fileConfig,
  onSubmit,
  disabled,
  placeholder = '描述你想要生成的内容…  支持 @ 引用素材，/ 唤起命令',
  startSlot,
}) => {
  const [text, setText] = useState('')
  const [showSlash, setShowSlash] = useState<'@' | '/' | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const files = useFileStore(s => s.files)
  const setFiles = useFileStore(s => s.setFiles)
  const clearFiles = useCallback(() => setFiles([]), [setFiles])

  const hasUploadingFiles = useMemo(
    () =>
      files.some(
        (f: FileEntity) =>
          f.transferMethod === TransferMethod.local_file && !f.uploadedId,
      ),
    [files],
  )

  const canSubmit
    = !disabled
      && (text.trim().length > 0 || files.length > 0)
      && !hasUploadingFiles

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === '@' || e.key === '/') {
        // Open the slash placeholder. We don't pre-empt the keystroke —
        // the character still goes into the textarea, the popover just
        // appears alongside.
        setShowSlash(e.key as '@' | '/')
        return
      }
      if (e.key === 'Escape') {
        setShowSlash(null)
        return
      }
      if (e.key === 'Enter' && !e.shiftKey && canSubmit) {
        e.preventDefault()
        onSubmit({ text: text.trim(), files })
        setText('')
        clearFiles()
        setShowSlash(null)
      }
    },
    [canSubmit, clearFiles, files, onSubmit, text],
  )

  const handleSendClick = useCallback(() => {
    if (!canSubmit)
      return
    onSubmit({ text: text.trim(), files })
    setText('')
    clearFiles()
    setShowSlash(null)
  }, [canSubmit, clearFiles, files, onSubmit, text])

  // Cast once so the JSX guards below can use proper truthiness checks
  // without TS narrowing the result of `?.fileUploadConfig` to `unknown`.
  // eslint-disable-next-line ts/no-explicit-any
  const fileConfigSafe = fileConfig as any
  const fileConfigReady = !!(fileConfigSafe && fileConfigSafe.fileUploadConfig)

  const renderUploadTrigger = useCallback(
    (_open: boolean) => (
      <button
        type="button"
        aria-label="上传文件"
        disabled={disabled}
        className="flex h-9 w-9 items-center justify-center rounded-full text-text-secondary hover:bg-state-base-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        <RiAttachment2 className="h-5 w-5" />
      </button>
    ),
    [disabled],
  )

  return (
    <div className="pointer-events-none absolute right-0 bottom-6 left-0 z-30 flex justify-center px-4">
      <div className="pointer-events-auto relative w-full max-w-2xl rounded-3xl border border-components-panel-border bg-components-panel-bg p-3 shadow-xl">
        {showSlash && (
          <div className="absolute right-3 bottom-full left-3 mb-2 rounded-xl border border-components-panel-border bg-components-panel-bg p-3 shadow-md">
            <div className="mb-1 system-2xs-medium-uppercase text-text-tertiary">
              {showSlash === '@' ? '引用' : '命令'}
            </div>
            {_SLASH_PLACEHOLDER.map(entry => (
              <div
                key={entry.id}
                className="flex items-center justify-between rounded-md px-2 py-1.5 system-sm-regular text-text-secondary"
              >
                <span className="system-sm-medium text-text-primary">
                  {entry.label}
                </span>
                <span className="system-xs-regular text-text-tertiary">
                  {entry.hint}
                </span>
              </div>
            ))}
          </div>
        )}
        {files.length > 0 && fileConfigReady && (
          <div className="mb-2">
            <FileListInChatInput fileConfig={fileConfigSafe} />
          </div>
        )}
        {startSlot}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={2}
          disabled={disabled}
          className={cn(
            'w-full resize-none border-0 bg-transparent px-2 py-1 system-md-regular text-text-primary outline-none',
            'placeholder:text-text-tertiary disabled:cursor-not-allowed',
          )}
        />
        <div className="mt-2 flex items-center justify-between">
          {/* useFile() crashes when fileConfig is undefined or missing
              .fileUploadConfig — gate the uploader so the page renders
              cleanly while the parent is still fetching app params. */}
          {fileConfigReady
            ? (
                <FileFromLinkOrLocal
                  trigger={renderUploadTrigger}
                  fileConfig={fileConfigSafe}
                  showFromLocal
                  showFromLink
                  placement="top"
                />
              )
            : (
                <span className="h-9 w-9" />
              )}
          <button
            type="button"
            aria-label="发送"
            onClick={handleSendClick}
            disabled={!canSubmit}
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-full text-white transition-colors',
              canSubmit
                ? 'cursor-pointer bg-components-button-primary-bg hover:bg-components-button-primary-bg-hover'
                : 'cursor-not-allowed bg-components-button-primary-bg-disabled',
            )}
          >
            <RiSendPlane2Fill className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Bottom-centred input dock for canvas-runtime.
 *
 * Wrapped in FileContextProvider so the `FileFromLinkOrLocal` +
 * `FileListInChatInput` pair shares the same scoped file store as
 * the rest of the chat surface (avoids files leaking into other
 * input boxes opened in the same browser tab).
 */
const RuntimeInput: FC<RuntimeInputProps> = props => (
  <FileContextProvider>
    <RuntimeInputInner {...props} />
  </FileContextProvider>
)

export default RuntimeInput
