'use client'

import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogCloseButton,
  DialogContent,
  DialogTitle,
} from '@/app/components/base/ui/dialog'
import { toast } from '@/app/components/base/ui/toast'
import {
  useAssetDetail,
  useDeleteAsset,
  usePatchAsset,
} from '@/service/use-asset-library'
import AssetPreview from './asset-preview'
import DeleteConfirmDialog from './delete-confirm-dialog'

type AssetDetailDrawerProps = {
  assetId: string | null
  onClose: () => void
  onMutated: () => void
}

type AssetDraft = {
  name: string
  description: string
  category: string
  tags: string[]
  content: string
}

const createDraft = (asset: AssetLibraryItem): AssetDraft => ({
  name: asset.name,
  description: asset.description ?? '',
  category: asset.category ?? '',
  tags: asset.tags,
  content: asset.content ?? '',
})

export default function AssetDetailDrawer({
  assetId,
  onClose,
  onMutated,
}: AssetDetailDrawerProps) {
  const { t } = useTranslation('assetLibrary')
  const { data: asset, isLoading } = useAssetDetail(assetId)

  if (!assetId)
    return null

  return (
    <Dialog
      open={!!assetId}
      onOpenChange={(open) => {
        if (!open)
          onClose()
      }}
    >
      <DialogContent className="top-0 right-0 left-auto h-dvh max-h-dvh w-[760px] max-w-[100vw] translate-x-0 translate-y-0 rounded-none border-y-0 border-r-0 p-0">
        <DialogCloseButton />
        {isLoading || !asset
          ? (
              <div className="flex h-full items-center justify-center text-sm text-text-tertiary">
                {t('detail.loading')}
              </div>
            )
          : (
              <AssetDetailForm
                key={asset.id}
                asset={asset}
                onClose={onClose}
                onMutated={onMutated}
              />
            )}
      </DialogContent>
    </Dialog>
  )
}

type AssetDetailFormProps = {
  asset: AssetLibraryItem
  onClose: () => void
  onMutated: () => void
}

function AssetDetailForm({
  asset,
  onClose,
  onMutated,
}: AssetDetailFormProps) {
  const { t } = useTranslation('assetLibrary')
  const patchAsset = usePatchAsset()
  const deleteAsset = useDeleteAsset()
  const [draft, setDraft] = useState(() => createDraft(asset))
  const [tagInput, setTagInput] = useState('')
  const [dirty, setDirty] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const updateDraft = <Key extends keyof AssetDraft>(
    key: Key,
    value: AssetDraft[Key],
  ) => {
    setDraft(prev => ({ ...prev, [key]: value }))
    setDirty(true)
  }

  const addTag = () => {
    const value = tagInput.trim()

    if (!value || draft.tags.includes(value)) {
      setTagInput('')
      return
    }

    updateDraft('tags', [...draft.tags, value])
    setTagInput('')
  }

  const removeTag = (tag: string) => {
    updateDraft('tags', draft.tags.filter(value => value !== tag))
  }

  const save = () => {
    patchAsset.mutate(
      {
        asset_id: asset.id,
        body: {
          name: draft.name.trim(),
          description: draft.description.trim() || null,
          tags: draft.tags,
          category: draft.category.trim() || null,
          ...(asset.asset_type === 'prompt'
            ? {
                content: draft.content,
                prompt_variables: asset.prompt_variables,
              }
            : {}),
        },
      },
      {
        onSuccess: () => {
          toast.success(t('detail.savedToast'))
          setDirty(false)
          onMutated()
        },
      },
    )
  }

  const confirmDelete = () => {
    deleteAsset.mutate(asset.id, {
      onSuccess: () => {
        toast.success(t('detail.deletedToast'))
        setDeleteOpen(false)
        onClose()
        onMutated()
      },
    })
  }

  return (
    <>
      <div className="flex h-full min-h-0 flex-col">
        <div className="border-b border-divider-subtle px-6 py-5">
          <DialogTitle className="pr-8 title-xl-semi-bold text-text-primary">
            {asset.name}
          </DialogTitle>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_320px]">
          <div className="flex min-h-0 items-center justify-center bg-background-section p-6">
            <AssetPreview asset={{ ...asset, content: draft.content }} />
          </div>

          <div className="flex min-h-0 flex-col border-l border-divider-subtle">
            <div className="flex-1 overflow-y-auto px-5 py-5">
              <div className="flex flex-col gap-4">
                <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
                  <span>{t('prompt.fields.name')}</span>
                  <input
                    type="text"
                    aria-label={t('prompt.fields.name')}
                    value={draft.name}
                    onChange={event => updateDraft('name', event.target.value)}
                    className="h-9 rounded-md border border-divider-subtle px-3 text-text-primary focus:border-primary-600 focus:outline-none"
                  />
                </label>

                <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
                  <span>{t('prompt.fields.description')}</span>
                  <textarea
                    aria-label={t('prompt.fields.description')}
                    value={draft.description}
                    onChange={event => updateDraft('description', event.target.value)}
                    rows={3}
                    className="rounded-md border border-divider-subtle px-3 py-2 text-text-primary focus:border-primary-600 focus:outline-none"
                  />
                </label>

                <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
                  <span>{t('prompt.fields.category')}</span>
                  <input
                    type="text"
                    aria-label={t('prompt.fields.category')}
                    value={draft.category}
                    onChange={event => updateDraft('category', event.target.value)}
                    className="h-9 rounded-md border border-divider-subtle px-3 text-text-primary focus:border-primary-600 focus:outline-none"
                  />
                </label>

                <div className="flex flex-col gap-1.5 text-sm text-text-secondary">
                  <span>{t('prompt.fields.tags')}</span>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {draft.tags.map(tag => (
                      <span
                        key={tag}
                        className="inline-flex h-7 items-center gap-1 rounded-full bg-background-section px-2 text-xs text-text-secondary"
                      >
                        {tag}
                        <button
                          type="button"
                          aria-label={t('filters.removeTag', { tag })}
                          onClick={() => removeTag(tag)}
                          className="flex h-4 w-4 items-center justify-center rounded-full text-text-tertiary hover:text-text-primary"
                        >
                          <span aria-hidden className="i-ri-close-line h-3 w-3" />
                        </button>
                      </span>
                    ))}
                    <input
                      type="text"
                      aria-label={t('prompt.fields.tags')}
                      value={tagInput}
                      onChange={event => setTagInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault()
                          addTag()
                        }
                      }}
                      placeholder={t('filters.tagsPlaceholder')}
                      className="h-9 min-w-36 flex-1 rounded-md border border-divider-subtle px-3 text-text-primary focus:border-primary-600 focus:outline-none"
                    />
                  </div>
                </div>

                {asset.asset_type === 'prompt' && (
                  <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
                    <span>{t('prompt.fields.content')}</span>
                    <textarea
                      aria-label={t('prompt.fields.content')}
                      value={draft.content}
                      onChange={event => updateDraft('content', event.target.value)}
                      rows={8}
                      className="rounded-md border border-divider-subtle px-3 py-2 text-text-primary focus:border-primary-600 focus:outline-none"
                    />
                  </label>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-divider-subtle px-5 py-4">
              <button
                type="button"
                onClick={() => setDeleteOpen(true)}
                className="rounded-md px-3 py-2 system-sm-medium text-text-destructive hover:bg-state-destructive-hover"
              >
                {t('detail.delete')}
              </button>
              <button
                type="button"
                onClick={save}
                disabled={!dirty || patchAsset.isPending}
                className="h-9 rounded-md bg-primary-600 px-3 system-sm-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t('detail.save')}
              </button>
            </div>
          </div>
        </div>
      </div>

      <DeleteConfirmDialog
        open={deleteOpen}
        name={asset.name}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={confirmDelete}
      />
    </>
  )
}
