'use client'

import type { ContentItemProps } from './type'
import * as React from 'react'
import { useMemo, useState, useEffect, useRef } from 'react'
import { cn } from '@/utils/classnames'
import { Markdown } from '@/app/components/base/markdown'

const ContentItemRefined = ({
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
    // If it starts with "### " or looks like a title, style it
    if (content.startsWith('#')) {
      return (
        <div className="mb-2 mt-6 flex items-center gap-2 text-base font-bold text-text-primary">
          <div className="h-4 w-1 rounded-full bg-primary-600" />
          {content.replace(/^#+\s*/, '')}
        </div>
      )
    }
    return <Markdown content={content} mode="static" className="text-text-secondary leading-relaxed" />
  }

  if (!formInputField)
    return null

  const value = inputs[fieldName] ?? ''

  const renderInput = () => {
    switch (formInputField.type) {
      case 'paragraph':
        return (
          <div className="group relative mt-2 overflow-hidden rounded-2xl border border-[#E9E9EB] bg-[#FBFBFF] transition-all focus-within:border-primary-300 focus-within:ring-4 focus-within:ring-primary-50">
            <textarea
              className="min-h-[120px] w-full resize-none border-none bg-transparent p-4 text-[15px] leading-relaxed text-text-primary outline-none focus:ring-0"
              value={value}
              onChange={(e) => onInputChange(fieldName, e.target.value)}
              placeholder="请输入内容..."
            />
            <button className="absolute bottom-3 right-3 flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-white shadow-sm transition-transform hover:scale-105 active:scale-95">
              <span className="i-ri-arrow-up-line h-4 w-4" />
            </button>
          </div>
        )

      case 'select':
        return (
          <div className="inline-block px-1">
            <select
              className="h-8 min-w-[80px] appearance-none rounded-lg border-none bg-[#F3E8FF] px-3 py-0 text-sm font-medium text-primary-700 outline-none transition-colors hover:bg-[#E9D5FF] focus:ring-2 focus:ring-primary-200"
              value={value}
              onChange={(e) => onInputChange(fieldName, e.target.value)}
            >
              {formInputField.options?.map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>
        )

      case 'text-input':
      default:
        return (
          <span className="inline-block px-1">
            <input
              className="h-8 min-w-[100px] rounded-lg border-none bg-[#F3E8FF] px-3 py-0 text-sm font-medium text-primary-700 outline-none transition-colors hover:bg-[#E9D5FF] focus:ring-2 focus:ring-primary-200"
              value={value}
              onChange={(e) => onInputChange(fieldName, e.target.value)}
              style={{ width: `${Math.max(value.length * 12 + 24, 100)}px` }}
            />
          </span>
        )
    }
  }

  // If it's an inline field (text-input or select), we might want to render it differently 
  // depending on surrounding content. For now, just wrap it.
  if (formInputField.type === 'paragraph') {
    return <div className="py-2">{renderInput()}</div>
  }

  return renderInput()
}

export default React.memo(ContentItemRefined)
