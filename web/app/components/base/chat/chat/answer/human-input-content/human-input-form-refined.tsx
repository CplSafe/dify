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

  // Group content items into sections based on screenshots
  // This is a bit tricky as the backend sends a single form_content string.
  // We'll rely on our splitByOutputVar but maybe wrap them in styled containers.

  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-4">
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
      
      <div className="flex items-center gap-3 pt-4">
        {formData.actions.map((action: UserAction) => (
          <button
            key={action.id}
            disabled={isSubmitting}
            onClick={() => submit(formToken, action.id, inputs)}
            className={cn(
              "h-10 px-6 rounded-xl font-medium transition-all active:scale-95 disabled:opacity-50",
              action.button_style === 'primary' 
                ? "bg-gradient-to-r from-[#80A7FF] to-[#B98DFF] text-white shadow-md hover:opacity-90"
                : "bg-white border border-[#E9E9EB] text-text-secondary hover:bg-[#F4F4F5]"
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
