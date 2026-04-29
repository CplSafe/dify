import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { upload } from './base'

export type UploadAssetFileBody = {
  file: File
  asset_type: 'image' | 'audio' | 'video'
  name?: string
  tags?: string[]
  category?: string
  description?: string
  onProgress?: (percent: number) => void
}

export const uploadAssetFile = async (
  body: UploadAssetFileBody,
): Promise<AssetLibraryItem> => {
  const fd = new FormData()
  fd.append('file', body.file)
  fd.append('asset_type', body.asset_type)

  if (body.name)
    fd.append('name', body.name)
  if (body.description)
    fd.append('description', body.description)

  fd.append('tags', JSON.stringify(body.tags ?? []))

  if (body.category)
    fd.append('category', body.category)

  const xhr = new XMLHttpRequest()
  if (body.onProgress) {
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        body.onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
  }

  const response = await upload(
    {
      xhr,
      data: fd,
      method: 'POST',
    },
    false,
    '/asset-library/files',
  )

  return response as AssetLibraryItem
}
