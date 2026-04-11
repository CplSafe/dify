import type { ContentItemProps } from './type'
import * as React from 'react'
import { useMemo } from 'react'
import Input from '@/app/components/base/input'
import { Markdown } from '@/app/components/base/markdown'
import Textarea from '@/app/components/base/textarea'

const ContentItem = ({
  content,
  formInputFields,
  inputs,
  onInputChange,
}: ContentItemProps) => {
  const isInputField = (field: string) => {
    const outputVarRegex = /\{\{#\$output\.[^#]+#\}\}/
    return outputVarRegex.test(field)
  }

  const extractFieldName = (str: string): string => {
    const outputVarRegex = /\{\{#\$output\.([^#]+)#\}\}/
    const match = outputVarRegex.exec(str)
    return match ? match[1] : ''
  }

  const fieldName = useMemo(() => {
    return extractFieldName(content)
  }, [content])

  const formInputField = useMemo(() => {
    return formInputFields.find(field => field.output_variable_name === fieldName)
  }, [formInputFields, fieldName])

  if (!isInputField(content)) {
    return (
      <Markdown content={content} mode="static" />
    )
  }

  if (!formInputField)
    return null

  const fieldOptions = (formInputField as { options?: string[] }).options || []

  return (
    <div className="py-3">
      {(formInputField.type === 'text-input' || formInputField.type === 'text_input') && (
        <Input
          size="large"
          value={inputs[fieldName] || ''}
          onChange={e => onInputChange(fieldName, e.target.value)}
          data-testid="content-item-input"
        />
      )}
      {formInputField.type === 'select' && (
        <select
          className="w-full rounded-lg border border-components-panel-border-subtle bg-components-input-bg-normal px-4 py-3 text-text-primary outline-hidden hover:border-components-input-border-hover focus:border-components-input-border-active"
          value={inputs[fieldName] || fieldOptions[0] || ''}
          onChange={e => onInputChange(fieldName, e.target.value)}
          data-testid="content-item-select"
        >
          {fieldOptions.map(option => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      )}
      {formInputField.type === 'paragraph' && (
        <Textarea
          className="h-[128px] rounded-xl sm:text-xs"
          value={inputs[fieldName]}
          onChange={(e) => { onInputChange(fieldName, e.target.value) }}
          data-testid="content-item-textarea"
        />
      )}
    </div>
  )
}

export default React.memo(ContentItem)
