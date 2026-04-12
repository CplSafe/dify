'use client'

import type { FileEntity } from '@/app/components/base/file-uploader/types'
import { useCallback, useState } from 'react'
import { FileFromLinkOrLocal, FileListInChatInput } from '@/app/components/base/file-uploader'
import { FileContextProvider, useStore } from '@/app/components/base/file-uploader/store'
import { SupportUploadFileTypes } from '@/app/components/workflow/types'
import { TransferMethod } from '@/types/app'
import { cn } from '@/utils/classnames'

// Icons (reconstructed from SVG)
const TiktokIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <g clipPath="url(#tiktok-icon-clip)">
      <path d="M7 1.166c1.75 1.167 2.288 3.67 2.333 5.833C9.288 9.162 8.75 11.666 7 12.833M7 1.166c-1.75 1.167-2.288 3.67-2.333 5.833.045 2.163.583 4.667 2.333 5.834M7 1.166a5.833 5.833 0 0 0-5.833 5.833M7 1.166a5.833 5.833 0 0 1 5.833 5.833M7 12.833a5.833 5.833 0 0 0 5.833-5.834M7 12.833a5.833 5.833 0 0 1-5.833-5.834m11.666 0C11.667 8.75 9.163 9.288 7 9.333c-2.163-.045-4.667-.584-5.833-2.334m11.666 0C11.667 5.25 9.163 4.711 7 4.666c-2.163.045-4.667.583-5.833 2.333" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
    </g>
    <defs>
      <clipPath id="tiktok-icon-clip">
        <rect width="14" height="14" fill="white"/>
      </clipPath>
    </defs>
  </svg>
)

const UploadIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="m8.333 2.916 1.75-1.75m0 0 1.75 1.75m-1.75-1.75v3.5M6.292 1.749H3.55c-.98 0-1.47 0-1.844.191a1.75 1.75 0 0 0-.765.765C.75 3.079.75 3.569.75 4.549v4.9c0 .98 0 1.47.19 1.845.169.33.436.597.766.765.374.19.864.19 1.844.19h5.367c.542 0 .813 0 1.036-.06a1.75 1.75 0 0 0 1.237-1.237c.06-.222.06-.493.06-1.036M5.125 4.958a1.167 1.167 0 1 1-2.333 0 1.167 1.167 0 0 1 2.333 0m2.62 1.994L2.81 11.437c-.278.253-.416.379-.429.488a.3.3 0 0 0 .098.252c.082.072.27.072.645.072h5.475c.84 0 1.26 0 1.59-.14a1.75 1.75 0 0 0 .92-.921c.141-.33.141-.75.141-1.59 0-.282 0-.423-.03-.555A1.2 1.2 0 0 0 11 8.59c-.083-.107-.194-.195-.414-.371L8.955 6.913c-.22-.176-.331-.265-.453-.296a.6.6 0 0 0-.325.01c-.119.04-.224.134-.433.325" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

const StarIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
    <g clipPath="url(#star-icon-clip)">
      <path d="M7.506.88c.17-.46.821-.46.992 0l.777 2.1a6.35 6.35 0 0 0 3.75 3.75l2.098.776c.46.17.46.821 0 .992l-2.099.777a6.35 6.35 0 0 0-3.75 3.749l-.776 2.1a.529.529 0 0 1-.992 0l-.777-2.1a6.35 6.35 0 0 0-3.75-3.75L.88 8.499a.529.529 0 0 1 0-.992l2.1-.777a6.35 6.35 0 0 0 3.75-3.75z" fill="white"/>
    </g>
    <defs>
      <clipPath id="star-icon-clip">
        <rect width="16" height="16" fill="white"/>
      </clipPath>
    </defs>
  </svg>
)

export type HomeInputProps = {
  onSubmit: (text: string, files: FileEntity[]) => void
  appParams?: any
}

function CreatorHomeInputContent({ onSubmit, appParams }: HomeInputProps) {
  const [value, setValue] = useState('')
  const [tiktokUrl, setTiktokUrl] = useState('')
  const [showTiktokInput, setShowTiktokInput] = useState(false)
  const files = useStore(state => state.files)

  const buildSubmitText = useCallback(() => {
    const content = value.trim()
    const tiktokContent = tiktokUrl.trim()

    if (showTiktokInput && tiktokContent)
      return content ? `${content}\n\n抖音商品: ${tiktokContent}` : `抖音商品: ${tiktokContent}`

    return content
  }, [showTiktokInput, tiktokUrl, value])

  const hasUploadingFiles = files.some(file => file.transferMethod === TransferMethod.local_file && !file.uploadedId)
  const canSubmit = !!buildSubmitText() || files.length > 0

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (canSubmit && !hasUploadingFiles)
        onSubmit(buildSubmitText(), files)
    }
  }

  const handleSubmit = useCallback(() => {
    if (canSubmit && !hasUploadingFiles)
      onSubmit(buildSubmitText(), files)
  }, [buildSubmitText, canSubmit, files, hasUploadingFiles, onSubmit])

  const visionConfig = appParams?.file_upload || {
    enabled: true,
    number_limits: 9,
    detail: 'high',
    transfer_methods: [TransferMethod.local_file, TransferMethod.remote_url],
    allowed_file_types: [SupportUploadFileTypes.image],
    allowed_file_extensions: ['.jpg', '.jpeg', '.png', '.webp', '.gif'],
    allowed_file_upload_methods: [TransferMethod.local_file, TransferMethod.remote_url],
  }

  const renderUploadTrigger = useCallback((open: boolean) => {
    return (
      <button 
        className={cn(
          "flex items-center gap-2 rounded-xl border border-[#E9E9EB] px-4 py-2 text-sm font-medium text-[#4D4D54] transition-all hover:bg-[#F4F4F5] hover:border-[#D1D1D6] active:scale-[0.98]",
          open && "bg-[#F4F4F5] border-[#D1D1D6]"
        )}
      >
        <UploadIcon />
        <span>上传</span>
      </button>
    )
  }, [])

  return (
    <div className="mx-auto w-full max-w-[720px] px-8 py-8">
      {/* Header Section */}
      <div className="mb-10 text-center">
        <h1 className="flex items-center justify-center gap-2 text-[44px] font-bold tracking-tight text-[#1D1C23]">
          <span>Hi, 欢迎使用</span>
          <span className="bg-gradient-to-r from-[#4D80FF] to-[#B98DFF] bg-clip-text text-transparent">创作Agent</span>
        </h1>
        <p className="mt-4 text-[16px] tracking-[0.4em] text-[#919099] font-medium">
          让 好 内 内容 快 人 一 步
        </p>
      </div>

      {/* Input Box with Gradient Border */}
      <div className="relative rounded-[28px] p-[3px] bg-gradient-to-r from-[#80A7FF] via-[#B98DFF] to-[#FF8DC7] shadow-[0_8px_40px_rgba(185,141,255,0.12)]">
        <div className="flex flex-col rounded-[25px] bg-white p-6">
          <div className="flex flex-col gap-2 min-h-[96px]">
            <FileListInChatInput fileConfig={visionConfig as any} />
            {showTiktokInput && (
              <div className="flex items-center gap-2 rounded-xl bg-[#F5F5F7] px-3 py-2">
                <TiktokIcon />
                <input 
                  autoFocus
                  className="flex-1 bg-transparent text-sm text-text-primary outline-none placeholder:text-text-quaternary"
                  placeholder="请输入抖音商品 URL 或 ID"
                  value={tiktokUrl}
                  onChange={e => setTiktokUrl(e.target.value)}
                />
                <button 
                  className="text-text-quaternary hover:text-text-secondary"
                  onClick={() => {
                    setShowTiktokInput(false)
                    setTiktokUrl('')
                  }}
                >
                  <span className="i-ri-close-line h-4 w-4" />
                </button>
              </div>
            )}
            <textarea
              className="w-full flex-1 resize-none border-none p-0 text-lg text-text-primary placeholder:text-text-quaternary focus:ring-0 focus:outline-none focus-visible:ring-0"
              placeholder="请输入您想要创作的内容"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
          <div className="mt-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button 
                className={cn(
                  "flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-all active:scale-[0.98]",
                  showTiktokInput 
                    ? "border-primary-600 bg-primary-50 text-primary-600" 
                    : "border-[#E9E9EB] text-[#4D4D54] hover:bg-[#F4F4F5] hover:border-[#D1D1D6]"
                )}
                onClick={() => setShowTiktokInput(!showTiktokInput)}
              >
                <TiktokIcon />
                <span>抖音商品URL/ID</span>
              </button>
              <FileFromLinkOrLocal
                trigger={renderUploadTrigger}
                fileConfig={visionConfig as any}
                showFromLocal={true}
                showFromLink={true}
              />
            </div>
            <button 
              className={cn(
                "flex h-12 w-12 items-center justify-center rounded-full bg-[#D4C3FF] text-white shadow-sm transition-all hover:shadow-md active:scale-95",
                canSubmit && !hasUploadingFiles ? "hover:bg-[#C2ACFF] cursor-pointer" : "opacity-50 grayscale cursor-not-allowed"
              )}
              disabled={!canSubmit || hasUploadingFiles}
              onClick={handleSubmit}
            >
              <StarIcon />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function CreatorHomeInput(props: HomeInputProps) {
  return (
    <FileContextProvider>
      <CreatorHomeInputContent {...props} />
    </FileContextProvider>
  )
}
