import type { FileEntity } from '@/app/components/base/file-uploader/types'
import { TransferMethod } from '@/types/app'

const CREATOR_HOME_DRAFT_STORAGE_KEY = 'creator-home-draft'

export type CreatorDraftFile = Omit<FileEntity, 'originalFile'>

export type CreatorChatDraft = {
  id: string
  message: string
  files: CreatorDraftFile[]
}

const isBrowser = () => typeof window !== 'undefined'

export const sanitizeDraftFiles = (files: FileEntity[]): CreatorDraftFile[] => {
  return files
    .filter(file => file.transferMethod !== TransferMethod.local_file || !!file.uploadedId)
    .map(({ originalFile, ...rest }) => rest)
}

export const saveCreatorHomeDraft = (draft: Omit<CreatorChatDraft, 'id'>) => {
  if (!isBrowser())
    return

  const payload: CreatorChatDraft = {
    id: crypto.randomUUID(),
    message: draft.message,
    files: draft.files,
  }

  window.sessionStorage.setItem(CREATOR_HOME_DRAFT_STORAGE_KEY, JSON.stringify(payload))
}

export const getCreatorHomeDraft = (): CreatorChatDraft | null => {
  if (!isBrowser())
    return null

  const raw = window.sessionStorage.getItem(CREATOR_HOME_DRAFT_STORAGE_KEY)
  if (!raw)
    return null

  try {
    const parsed = JSON.parse(raw) as CreatorChatDraft
    if (!parsed?.id)
      return null
    return parsed
  }
  catch {
    return null
  }
}

export const clearCreatorHomeDraft = () => {
  if (!isBrowser())
    return

  window.sessionStorage.removeItem(CREATOR_HOME_DRAFT_STORAGE_KEY)
}
