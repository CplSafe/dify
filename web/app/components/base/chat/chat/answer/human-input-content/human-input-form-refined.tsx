'use client'

import type { HumanInputFormProps } from './type'
import type { UserAction } from '@/app/components/workflow/nodes/human-input/types'
import * as React from 'react'
import { useCallback, useState } from 'react'
import { cn } from '@/utils/classnames'
import ContentItemRefined from './content-item-refined'
import { initializeInputs, splitByOutputVar } from './utils'

const HumanInputFormRefined = ({
  formData,
  onSubmit,
}: HumanInputFormProps) => {
  const formToken = formData.form_token
  const defaultInputs = initializeInputs(formData.inputs, formData.resolved_default_values || {})
  const contentList = splitByOutputVar(formData.form_content)
  const [inputs, setInputs] = useState(defaultInputs)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleInputsChange = useCallback((name: string, value: string) => {
    setInputs(prev => ({
      ...prev,
      [name]: value,
    }))
  }, [])

  const submit = async (formToken: string, actionID: string, inputs: Record<string, string>) => {
    setIsSubmitting(true)
    try {
      await onSubmit?.(formToken, { inputs, action: actionID })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-7">
      <div className="space-y-3">
        {contentList.map((content, idx) => (
          <ContentItemRefined
            key={`${formData.node_id}-${idx}`}
            content={content}
            formInputFields={formData.inputs}
            inputs={inputs}
            onInputChange={handleInputsChange}
          />
        ))}
      </div>

      <div className="flex items-center gap-3 pt-2">
        {formData.actions.map((action: UserAction) => (
          <button
            key={action.id}
            type="button"
            disabled={isSubmitting}
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              void submit(formToken, action.id, inputs)
            }}
            className={cn(
              'inline-flex h-10 items-center rounded-xl px-5 text-[15px] font-medium transition-all active:scale-95 disabled:opacity-50',
              action.button_style === 'primary'
                ? 'bg-[#7C3AED] text-white shadow-[0_10px_24px_rgba(124,58,237,0.18)] hover:bg-[#6D28D9]'
                : 'border border-[#E7E4F5] bg-white text-[#4C4568] hover:bg-[#F7F4FF]'
            )}
          >
            {action.title}
          </button>
        ))}
      </div>
    </div>
  )
}

export default React.memo(HumanInputFormRefined)
