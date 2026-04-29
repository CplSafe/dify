'use client'

import type { PromptVariable } from '@/contract/console/asset-library'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/app/components/base/ui/dialog'
import { toast } from '@/app/components/base/ui/toast'
import { useCreatePromptAsset } from '@/service/use-asset-library'

const VARIABLE_NAME_PATTERN = /^[A-Z_]\w*$/i

type PromptDialogProps = {
  onCreated: () => void
}

type PromptVariableDraft = PromptVariable & {
  id: string
}

const createEmptyVariable = (): PromptVariableDraft => ({
  id: `${Date.now()}-${Math.random()}`,
  name: '',
  type: 'string',
  default: null,
  description: null,
})

const toPromptVariable = (variable: PromptVariableDraft): PromptVariable => ({
  name: variable.name,
  type: variable.type,
  default: variable.default,
  description: variable.description,
})

export default function PromptDialog({ onCreated }: PromptDialogProps) {
  const { t } = useTranslation('assetLibrary')
  const createPrompt = useCreatePromptAsset()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [variables, setVariables] = useState<PromptVariableDraft[]>([])
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setName('')
    setContent('')
    setDescription('')
    setCategory('')
    setTagInput('')
    setTags([])
    setVariables([])
    setError(null)
  }

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (!nextOpen)
      reset()
  }

  const addTag = () => {
    const value = tagInput.trim()

    if (!value || tags.includes(value)) {
      setTagInput('')
      return
    }

    setTags(prev => [...prev, value])
    setTagInput('')
  }

  const removeTag = (tag: string) => {
    setTags(prev => prev.filter(value => value !== tag))
  }

  const addVariable = () => {
    setVariables(prev => [...prev, createEmptyVariable()])
  }

  const removeVariable = (index: number) => {
    setVariables(prev => prev.filter((_, currentIndex) => currentIndex !== index))
  }

  const updateVariable = (
    index: number,
    patch: Partial<PromptVariable>,
  ) => {
    setVariables(prev =>
      prev.map((variable, currentIndex) =>
        currentIndex === index ? { ...variable, ...patch } : variable))
  }

  const validate = () => {
    if (!name.trim())
      return t('prompt.validation.nameRequired')

    if (!content.trim())
      return t('prompt.validation.contentRequired')

    if (variables.some(variable => !VARIABLE_NAME_PATTERN.test(variable.name)))
      return t('prompt.validation.variableNameInvalid')

    return null
  }

  const submit = async () => {
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    setError(null)

    try {
      await createPrompt.mutateAsync({
        name: name.trim(),
        content,
        prompt_variables: variables.map(toPromptVariable),
        description: description.trim() || null,
        tags,
        category: category.trim() || null,
      })
      toast.success(t('detail.savedToast'))
      onCreated()
      setOpen(false)
      reset()
    }
    catch (caughtError: unknown) {
      const reason = caughtError instanceof Error
        ? caughtError.message
        : 'unknown'
      setError(t('errors.validationFailed', { reason }))
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="h-9 rounded-md bg-primary-600 px-3 text-sm font-medium text-white"
      >
        {t('prompt.newButton')}
      </button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="w-[640px] max-w-[calc(100vw-2rem)]">
          <DialogTitle className="text-base font-semibold text-text-primary">
            {t('prompt.dialogTitle')}
          </DialogTitle>

          <div className="mt-5 flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
              <span>{t('prompt.fields.name')}</span>
              <input
                type="text"
                aria-label={t('prompt.fields.name')}
                value={name}
                onChange={event => setName(event.target.value)}
                className="h-9 rounded-md border border-divider-subtle px-3 text-text-primary focus:border-primary-600 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
              <span>{t('prompt.fields.content')}</span>
              <textarea
                aria-label={t('prompt.fields.content')}
                value={content}
                onChange={event => setContent(event.target.value)}
                rows={8}
                className="rounded-md border border-divider-subtle px-3 py-2 text-text-primary focus:border-primary-600 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
              <span>{t('prompt.fields.description')}</span>
              <textarea
                aria-label={t('prompt.fields.description')}
                value={description}
                onChange={event => setDescription(event.target.value)}
                rows={2}
                className="rounded-md border border-divider-subtle px-3 py-2 text-text-primary focus:border-primary-600 focus:outline-none"
              />
            </label>

            <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
              <span>{t('prompt.fields.category')}</span>
              <input
                type="text"
                aria-label={t('prompt.fields.category')}
                value={category}
                onChange={event => setCategory(event.target.value)}
                className="h-9 rounded-md border border-divider-subtle px-3 text-text-primary focus:border-primary-600 focus:outline-none"
              />
            </label>

            <div className="flex flex-col gap-1.5 text-sm text-text-secondary">
              <span>{t('prompt.fields.tags')}</span>
              <div className="flex flex-wrap items-center gap-1.5">
                {tags.map(tag => (
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
                  className="h-9 min-w-44 rounded-md border border-divider-subtle px-3 text-text-primary focus:border-primary-600 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-secondary">
                  {t('prompt.fields.variables')}
                </span>
                <button
                  type="button"
                  onClick={addVariable}
                  className="inline-flex h-8 items-center gap-1 rounded-md border border-divider-subtle px-2 text-xs text-text-secondary"
                >
                  <span aria-hidden className="i-ri-add-line h-4 w-4" />
                  {t('prompt.fields.addVariable')}
                </button>
              </div>

              {variables.map((variable, index) => (
                <div
                  key={variable.id}
                  className="grid grid-cols-[1fr_120px_1fr_1fr_32px] gap-2"
                >
                  <input
                    type="text"
                    aria-label={t('prompt.variableFields.name')}
                    value={variable.name}
                    onChange={event =>
                      updateVariable(index, { name: event.target.value })}
                    placeholder={t('prompt.variableFields.name')}
                    className="h-9 rounded-md border border-divider-subtle px-3 text-sm focus:border-primary-600 focus:outline-none"
                  />
                  <select
                    aria-label={t('prompt.variableFields.type')}
                    value={variable.type}
                    onChange={event =>
                      updateVariable(index, {
                        type: event.target.value as PromptVariable['type'],
                        default: null,
                      })}
                    className="h-9 rounded-md border border-divider-subtle px-3 text-sm focus:border-primary-600 focus:outline-none"
                  >
                    <option value="string">{t('prompt.variableTypes.string')}</option>
                    <option value="number">{t('prompt.variableTypes.number')}</option>
                    <option value="boolean">{t('prompt.variableTypes.boolean')}</option>
                  </select>
                  <input
                    type="text"
                    aria-label={t('prompt.variableFields.default')}
                    value={String(variable.default ?? '')}
                    onChange={event =>
                      updateVariable(index, {
                        default: event.target.value || null,
                      })}
                    placeholder={t('prompt.variableFields.default')}
                    className="h-9 rounded-md border border-divider-subtle px-3 text-sm focus:border-primary-600 focus:outline-none"
                  />
                  <input
                    type="text"
                    aria-label={t('prompt.variableFields.description')}
                    value={variable.description ?? ''}
                    onChange={event =>
                      updateVariable(index, {
                        description: event.target.value || null,
                      })}
                    placeholder={t('prompt.variableFields.description')}
                    className="h-9 rounded-md border border-divider-subtle px-3 text-sm focus:border-primary-600 focus:outline-none"
                  />
                  <button
                    type="button"
                    aria-label={t('prompt.variableFields.remove')}
                    onClick={() => removeVariable(index)}
                    className="flex h-9 w-8 items-center justify-center rounded-md border border-divider-subtle text-text-tertiary hover:text-text-primary"
                  >
                    <span aria-hidden className="i-ri-close-line h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>

            {error && (
              <p className="text-sm text-text-destructive">{error}</p>
            )}
          </div>

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => handleOpenChange(false)}
              className="h-9 rounded-md border border-divider-subtle px-3 text-sm text-text-secondary"
            >
              {t('prompt.cancel')}
            </button>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={createPrompt.isPending}
              className="h-9 rounded-md bg-primary-600 px-3 text-sm font-medium text-white disabled:opacity-50"
            >
              {t('prompt.create')}
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
