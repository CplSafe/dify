'use client'

import type { ContentItemProps } from './type'
import * as React from 'react'
import { useMemo } from 'react'
import { Markdown } from '@/app/components/base/markdown'

const tagClassName = 'inline-flex min-h-8 items-center rounded-[10px] bg-[#F2ECFF] px-3 py-1 text-[14px] font-medium text-[#6D28D9] shadow-[inset_0_0_0_1px_rgba(167,139,250,0.15)]'

const renderMediaPreview = (value: any) => {
  const files = Array.isArray(value) ? value : value ? [value] : []
  if (!files.length)
    return null

  return (
    <div className="mt-3 flex flex-wrap gap-3">
      {files.map((file: any, index: number) => {
        const src = file?.url || file?.preview_url || file?.download_url
        if (!src)
          return null

        return (
          <div
            key={`${src}-${index}`}
            className="flex h-[72px] w-[72px] items-center justify-center overflow-hidden rounded-2xl border border-[#E7E4F5] bg-[#FAF8FF]"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={src} alt={file?.name || 'media'} className="h-full w-full object-cover" />
          </div>
        )
      })}
    </div>
  )
}

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
    if (content.startsWith('#')) {
      return (
        <div className="mt-5 flex items-center gap-2 text-[16px] font-semibold text-[#2D2942] first:mt-0">
          <span className="i-ri-arrow-down-s-line h-4 w-4 text-[#8B5CF6]" />
          <span>{content.replace(/^#+\s*/, '')}</span>
        </div>
      )
    }
    return (
      <div className="text-[15px] leading-8 text-[#59556B]">
        <Markdown content={content} mode="static" className="text-[15px] leading-8 text-[#59556B]" />
      </div>
    )
  }

  if (!formInputField)
    return null

  const value = inputs[fieldName] ?? ''

  const renderInput = () => {
    switch (formInputField.type) {
      case 'paragraph':
        return (
          <div className="mt-3 overflow-hidden rounded-2xl border border-[#E7E4F5] bg-[#FBFAFF] transition-all focus-within:border-[#C4B5FD] focus-within:ring-4 focus-within:ring-[#F3E8FF]">
            <textarea
              className="min-h-[120px] w-full resize-none border-none bg-transparent p-4 text-[15px] leading-7 text-[#2D2942] outline-none focus:ring-0"
              value={value}
              onChange={(e) => onInputChange(fieldName, e.target.value)}
              placeholder="请输入内容..."
            />
          </div>
        )

      case 'select':
        return (
          <span className="inline-flex px-1 align-middle">
            <select
              className={`${tagClassName} min-w-[88px] appearance-none border-none pr-8 outline-none transition-colors hover:bg-[#E9D5FF] focus:ring-2 focus:ring-[#DDD6FE]`}
              value={value}
              onChange={(e) => onInputChange(fieldName, e.target.value)}
            >
              {formInputField.options?.map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </span>
        )

      case 'text-input':
      case 'text_input':
      case 'url':
      case 'number':
        return (
          <span className="inline-flex px-1 align-middle">
            <input
              className={`${tagClassName} min-w-[96px] border-none outline-none transition-colors hover:bg-[#E9D5FF] focus:ring-2 focus:ring-[#DDD6FE]`}
              value={value}
              onChange={(e) => onInputChange(fieldName, e.target.value)}
              style={{ width: `${Math.max(String(value).length * 12 + 32, 112)}px` }}
            />
          </span>
        )

      case 'file':
      case 'file-list':
      case 'files':
        return renderMediaPreview(value)

      default:
        return <span className={tagClassName}>{String(value || '')}</span>
    }
  }

  if (formInputField.type === 'paragraph') {
    return <div className="py-1">{renderInput()}</div>
  }

  return renderInput()
}

export default React.memo(ContentItemRefined)
