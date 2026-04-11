import type { ChangeEvent } from 'react'
import type { ContentItemProps } from './type'
import * as React from 'react'
import { useMemo } from 'react'
import Input from '@/app/components/base/input'
import { Markdown } from '@/app/components/base/markdown'
import Textarea from '@/app/components/base/textarea'
import BoolInput from '@/app/components/workflow/nodes/_base/components/before-run-form/bool-input'
import CodeEditor from '@/app/components/workflow/nodes/_base/components/editor/code-editor'
import { CodeLanguage } from '@/app/components/workflow/nodes/code/types'

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
    return formInputFields.find(
      field => field.output_variable_name === fieldName,
    )
  }, [formInputFields, fieldName])

  if (!isInputField(content)) {
    return <Markdown content={content} mode="static" />
  }

  if (!formInputField)
    return null

  const renderInput = () => {
    const fieldOptions = (formInputField as { options?: string[] }).options || []

    switch (formInputField.type) {
      case 'paragraph':
        return (
          <Textarea
            className="h-[128px] rounded-xl sm:text-xs"
            value={inputs[fieldName] ?? ''}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
              onInputChange(fieldName, e.target.value)
            }}
            data-testid="content-item-textarea"
          />
        )

      case 'text-input':
      case 'text_input':
      case 'url':
        return (
          <Input
            type={formInputField.type === 'url' ? 'url' : 'text'}
            size="large"
            value={inputs[fieldName] ?? ''}
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              onInputChange(fieldName, e.target.value)
            }}
            data-testid="content-item-input"
          />
        )

      case 'number':
        return (
          <Input
            type="number"
            value={inputs[fieldName] ?? ''}
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              onInputChange(fieldName, e.target.value)
            }}
            data-testid="content-item-number-input"
          />
        )

      case 'select':
        return (
          <select
            className="w-full rounded-lg border border-components-panel-border-subtle bg-components-input-bg-normal px-4 py-3 text-text-primary outline-hidden hover:border-components-input-border-hover focus:border-components-input-border-active"
            value={inputs[fieldName] ?? fieldOptions[0] ?? ''}
            onChange={(e) => {
              onInputChange(fieldName, e.target.value)
            }}
            data-testid="content-item-select"
          >
            {fieldOptions.map(option => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
        )

      case 'checkbox':
        return (
          <BoolInput
            name={fieldName}
            value={inputs[fieldName] === 'true'}
            onChange={(value) => {
              onInputChange(fieldName, String(value))
            }}
          />
        )

      case 'json':
      case 'json_object':
        return (
          <CodeEditor
            language={CodeLanguage.json}
            value={inputs[fieldName] ?? ''}
            onChange={(value) => {
              onInputChange(fieldName, value)
            }}
            noWrapper
            className="h-[80px] overflow-y-auto radius-lg bg-components-input-bg-normal p-1"
          />
        )

      default:
        return (
          <Input
            type="text"
            value={inputs[fieldName] ?? ''}
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              onInputChange(fieldName, e.target.value)
            }}
            data-testid="content-item-fallback-input"
          />
        )
    }
  }

  return <div className="py-3">{renderInput()}</div>
}

export default React.memo(ContentItem)
