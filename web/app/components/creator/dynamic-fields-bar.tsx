'use client'
/* eslint-disable ts/no-explicit-any, no-restricted-imports, tailwindcss/enforce-consistent-class-order, hyoban/prefer-tailwind-icons -- aligned with creator/home-input.tsx style; overlay primitives migration tracked in #32767 */

/**
 * Dynamic input bar for creator home — renders one icon button per
 * non-file field declared on the workflow start node. Icon shows a tooltip
 * on hover; click opens a small popover with the type-appropriate input.
 *
 * File-type fields (singleFile / multiFiles) are rendered separately by
 * the parent because they need to integrate with the existing
 * FileFromLinkOrLocal upload flow.
 */
import {
  RiArrowDownSLine,
  RiCheckLine,
  RiHashtag,
  RiInputField,
  RiListCheck,
  RiTextBlock,
} from '@remixicon/react'
import { useState } from 'react'
import {
  PortalToFollowElem,
  PortalToFollowElemContent,
  PortalToFollowElemTrigger,
} from '@/app/components/base/portal-to-follow-elem'
import Tooltip from '@/app/components/base/tooltip'
import { InputVarType } from '@/app/components/workflow/types'
import { cn } from '@/utils/classnames'

export type DynamicField = {
  variable: string
  label: string
  type: InputVarType
  required?: boolean
  default?: string | number
  // select-only
  options?: string[]
  // text/paragraph-only
  max_length?: number
  placeholder?: string
  hint?: string
}

type Props = {
  fields: DynamicField[]
  values: Record<string, any>
  onChange: (variable: string, value: any) => void
}

const ICON_FOR: Record<string, React.ComponentType<{ className?: string }>> = {
  [InputVarType.textInput]: RiInputField,
  [InputVarType.textInputUnderscore]: RiInputField,
  [InputVarType.paragraph]: RiTextBlock,
  [InputVarType.select]: RiListCheck,
  [InputVarType.number]: RiHashtag,
}

const isTextLike = (t: InputVarType) =>
  t === InputVarType.textInput
  || t === InputVarType.textInputUnderscore
  || t === InputVarType.paragraph
  || t === InputVarType.number

const isMultiLine = (t: InputVarType) => t === InputVarType.paragraph

const summarizeValue = (value: any): string => {
  if (value === null || value === undefined || value === '')
    return ''
  const s = String(value)
  return s.length > 12 ? `${s.slice(0, 10)}…` : s
}

function FieldChip({
  field,
  value,
  onChange,
}: {
  field: DynamicField
  value: any
  onChange: (v: any) => void
}) {
  const [open, setOpen] = useState(false)
  const Icon = ICON_FOR[field.type] || RiInputField
  const summary = summarizeValue(value)
  const hasValue = summary !== ''

  // 「行业选择」(industry) 业务上目前只支持「爱玛」，其它选项标注「敬请期待」
  const decorateOption = (variable: string, option: string) =>
    variable === 'industry' && option !== '爱玛'
      ? `${option}（敬请期待）`
      : option

  return (
    <PortalToFollowElem
      open={open}
      onOpenChange={setOpen}
      placement="top-start"
      offset={6}
    >
      <PortalToFollowElemTrigger onClick={() => setOpen(o => !o)}>
        <Tooltip
          popupContent={(
            <div className="max-w-[240px]">
              <div className="font-medium text-text-primary">{field.label}</div>
              {field.hint && (
                <div className="mt-1 text-xs text-text-tertiary">
                  {field.hint}
                </div>
              )}
              {hasValue && (
                <div className="mt-1 text-xs text-text-secondary">
                  当前:
                  {' '}
                  {String(value)}
                </div>
              )}
            </div>
          )}
        >
          <button
            type="button"
            className={cn(
              'flex h-9 items-center gap-1.5 rounded-xl border px-3 text-sm font-medium transition-all active:scale-[0.98]',
              hasValue
                ? 'border-primary-600 bg-primary-50 text-primary-600'
                : 'border-[#E9E9EB] text-[#4D4D54] hover:border-[#D1D1D6] hover:bg-[#F4F4F5]',
            )}
            aria-label={field.label}
          >
            <Icon className="h-4 w-4" />
            <span className="max-w-[120px] truncate">{field.label}</span>
            {hasValue && (
              <span className="ml-1 max-w-[80px] truncate rounded bg-white/70 px-1.5 py-0.5 text-xs">
                {summary}
              </span>
            )}
            <RiArrowDownSLine className="h-4 w-4 opacity-60" />
          </button>
        </Tooltip>
      </PortalToFollowElemTrigger>
      <PortalToFollowElemContent className="z-[60]">
        <div className="w-[280px] rounded-xl border border-divider-subtle bg-components-panel-bg p-3 shadow-lg">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-text-primary">
              {field.label}
            </span>
            {field.required && (
              <span className="text-xs text-text-warning">必填</span>
            )}
          </div>

          {field.type === InputVarType.select && (
            <div className="flex flex-col gap-0.5">
              {(field.options || []).map((option) => {
                const selected = value === option
                return (
                  <button
                    key={option}
                    type="button"
                    onClick={() => {
                      onChange(option)
                      setOpen(false)
                    }}
                    className={cn(
                      'flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-state-base-hover',
                      selected ? 'text-primary-600' : 'text-text-secondary',
                    )}
                  >
                    <span className="truncate">
                      {decorateOption(field.variable, option)}
                    </span>
                    {selected && <RiCheckLine className="h-4 w-4" />}
                  </button>
                )
              })}
            </div>
          )}

          {isTextLike(field.type) && !isMultiLine(field.type) && (
            <input
              type={field.type === InputVarType.number ? 'number' : 'text'}
              className="w-full rounded-md border border-[#E9E9EB] bg-components-input-bg-normal px-2 py-1.5 text-sm text-text-primary outline-none focus:border-primary-600"
              value={value ?? ''}
              maxLength={field.max_length}
              placeholder={field.placeholder || `请输入${field.label}`}
              onChange={e => onChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter')
                  setOpen(false)
              }}
              autoFocus
            />
          )}

          {isMultiLine(field.type) && (
            <textarea
              className="w-full resize-none rounded-md border border-[#E9E9EB] bg-components-input-bg-normal px-2 py-1.5 text-sm text-text-primary outline-none focus:border-primary-600"
              rows={5}
              value={value ?? ''}
              maxLength={field.max_length}
              placeholder={field.placeholder || `请输入${field.label}`}
              onChange={e => onChange(e.target.value)}
              autoFocus
            />
          )}

          <div className="mt-2 flex justify-end gap-2">
            {hasValue && (
              <button
                type="button"
                className="rounded-md px-2 py-1 text-xs text-text-tertiary hover:bg-state-base-hover"
                onClick={() => {
                  onChange('')
                  setOpen(false)
                }}
              >
                清除
              </button>
            )}
            <button
              type="button"
              className="rounded-md bg-primary-600 px-3 py-1 text-xs text-white hover:bg-primary-700"
              onClick={() => setOpen(false)}
            >
              完成
            </button>
          </div>
        </div>
      </PortalToFollowElemContent>
    </PortalToFollowElem>
  )
}

export default function DynamicFieldsBar({ fields, values, onChange }: Props) {
  if (fields.length === 0)
    return null
  return (
    <>
      {fields.map(field => (
        <FieldChip
          key={field.variable}
          field={field}
          value={values[field.variable]}
          onChange={v => onChange(field.variable, v)}
        />
      ))}
    </>
  )
}
