'use client'

import type { AssetType } from '@/contract/console/asset-library'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/app/components/base/ui/toast'
import { useUploadAssetFile } from '@/service/use-asset-library'

const MAX_SIZE_BYTES = 200 * 1024 * 1024

const MIME_TYPE_MAP: Record<string, Exclude<AssetType, 'prompt'>> = {
  'audio/mpeg': 'audio',
  'audio/mp4': 'audio',
  'audio/wav': 'audio',
  'image/gif': 'image',
  'image/jpeg': 'image',
  'image/png': 'image',
  'image/webp': 'image',
  'video/mp4': 'video',
  'video/quicktime': 'video',
}

type ProgressItem = {
  id: string
  filename: string
  percent: number
  error?: string
}

type UploadDropzoneProps = {
  defaultAssetType: Exclude<AssetType, 'prompt'>
  onUploaded: () => void
}

export default function UploadDropzone({ onUploaded }: UploadDropzoneProps) {
  const { t } = useTranslation('assetLibrary')
  const upload = useUploadAssetFile()
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<ProgressItem[]>([])

  const updateProgress = (id: string, patch: Partial<ProgressItem>) => {
    setProgress(prev =>
      prev.map(item => item.id === id ? { ...item, ...patch } : item))
  }

  const removeProgress = (id: string) => {
    setProgress(prev => prev.filter(item => item.id !== id))
  }

  const startUpload = async (file: File) => {
    if (file.size > MAX_SIZE_BYTES) {
      toast.error(t('upload.fileTooLarge'))
      return
    }

    const assetType = MIME_TYPE_MAP[file.type]
    if (!assetType) {
      toast.error(t('upload.unsupportedMime', { mime: file.type || 'unknown' }))
      return
    }

    const id = `${file.name}-${file.size}-${Date.now()}-${Math.random()}`
    setProgress(prev => [
      ...prev,
      { id, filename: file.name, percent: 0 },
    ])

    try {
      await upload.mutateAsync({
        file,
        asset_type: assetType,
        name: file.name,
        onProgress: percent => updateProgress(id, { percent }),
      })
      removeProgress(id)
      onUploaded()
    }
    catch (error: unknown) {
      const reason = error instanceof Error ? error.message : 'upload failed'
      updateProgress(id, { error: reason })
    }
  }

  const handleFiles = (files: FileList | File[]) => {
    Array.from(files).forEach(file => void startUpload(file))
  }

  return (
    <div className="my-3">
      <label
        data-testid="asset-dropzone"
        onDragEnter={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          handleFiles(event.dataTransfer.files)
        }}
        className={[
          'flex h-28 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed transition-colors',
          dragging
            ? 'border-primary-600 bg-primary-50'
            : 'border-divider-subtle bg-background-section',
        ].join(' ')}
      >
        <input
          type="file"
          multiple
          className="hidden"
          onChange={(event) => {
            handleFiles(event.currentTarget.files ?? [])
            event.currentTarget.value = ''
          }}
        />
        <span
          aria-hidden
          className="mb-1 i-ri-upload-cloud-2-line h-6 w-6 text-text-tertiary"
        />
        <span className="text-sm text-text-tertiary">
          {dragging ? t('upload.dropzoneActive') : t('upload.dropzoneIdle')}
        </span>
      </label>
      {progress.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {progress.map(item => (
            <div
              key={item.id}
              className={[
                'flex h-7 items-center gap-2 rounded-full px-3 text-xs',
                item.error
                  ? 'bg-state-destructive-50 text-state-destructive'
                  : 'bg-background-section text-text-secondary',
              ].join(' ')}
            >
              <span className="max-w-40 truncate">
                {item.error
                  ? t('upload.uploadFailed', { reason: item.error })
                  : t('upload.uploading', { filename: item.filename })}
              </span>
              {!item.error && (
                <span>
                  {item.percent}
                  %
                </span>
              )}
              {item.error && (
                <button
                  type="button"
                  aria-label={t('upload.dismissProgress')}
                  onClick={() => removeProgress(item.id)}
                  className="flex h-4 w-4 items-center justify-center rounded-full"
                >
                  <span aria-hidden className="i-ri-close-line h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
