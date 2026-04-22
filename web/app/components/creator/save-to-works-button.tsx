'use client'

import type { FC } from 'react'
import { useCallback, useState } from 'react'
import { toast } from '@/app/components/base/ui/toast'
import { useRouter } from '@/next/navigation'
import { createCreatorWork } from '@/service/creator-work'

type SaveToWorksButtonProps = {
  fileUrl: string
  fileType: 'image' | 'video'
}

const SaveToWorksButton: FC<SaveToWorksButtonProps> = ({
  fileUrl,
  fileType,
}) => {
  const router = useRouter()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // Button label: 「保存视频/图片至发布作品」
  // After saving, jump to the works page so the user immediately sees
  // the new draft and can choose where to publish it.
  const label
    = fileType === 'video' ? '保存视频至发布作品' : '保存图片至发布作品'

  const handleSave = useCallback(async () => {
    if (saving || saved)
      return

    setSaving(true)
    try {
      await createCreatorWork({
        title: fileType === 'video' ? '视频作品' : '图片作品',
        file_key: fileUrl,
        file_type: fileType,
      })
      setSaved(true)
      toast.success('已保存，正在跳转到发布作品...')
      router.push('/creator-works')
    }
    catch {
      toast.error('保存失败，请重试')
    }
    finally {
      setSaving(false)
    }
  }, [fileUrl, fileType, saving, saved, router])

  if (saved) {
    return (
      <button
        type="button"
        disabled
        className="mt-1 inline-flex items-center gap-1 rounded-lg bg-util-colors-green-green-50 px-2.5 py-1 text-xs font-medium text-util-colors-green-green-600"
      >
        <span aria-hidden className="i-ri-check-line h-3.5 w-3.5" />
        <span>已保存</span>
      </button>
    )
  }

  return (
    <button
      type="button"
      disabled={saving}
      onClick={handleSave}
      className="mt-1 inline-flex items-center gap-1 rounded-lg bg-components-button-secondary-bg px-2.5 py-1 text-xs font-medium text-components-button-secondary-text shadow-xs transition-colors hover:bg-components-button-secondary-bg-hover disabled:opacity-50"
    >
      <span aria-hidden className="i-ri-download-cloud-2-line h-3.5 w-3.5" />
      <span>{saving ? '保存中...' : label}</span>
    </button>
  )
}

export default SaveToWorksButton
