'use client'
/* eslint-disable ts/no-explicit-any, no-restricted-imports, hyoban/prefer-tailwind-icons -- aligned with creator/home-input.tsx style; overlay primitives migration tracked in #32767 */

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
  RiAspectRatioLine,
  RiBuilding2Line,
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

type IconComp = React.ComponentType<{ className?: string }>

const ICON_FOR: Record<string, IconComp> = {
  [InputVarType.textInput]: RiInputField,
  [InputVarType.textInputUnderscore]: RiInputField,
  [InputVarType.paragraph]: RiTextBlock,
  [InputVarType.select]: RiListCheck,
  [InputVarType.number]: RiHashtag,
}

// Variable-name overrides — use a more meaningful icon when we can guess
// the field's purpose from its variable name. Falls back to ICON_FOR.
const ICON_BY_VARIABLE: Record<string, IconComp> = {
  industry: RiBuilding2Line,
  item: RiAspectRatioLine, // 「选择比例」
  ratio: RiAspectRatioLine,
  aspect: RiAspectRatioLine,
  size: RiAspectRatioLine,
}

const resolveIcon = (field: DynamicField): IconComp => {
  const byVariable = ICON_BY_VARIABLE[field.variable.toLowerCase()]
  if (byVariable)
    return byVariable
  return ICON_FOR[field.type] || RiInputField
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

// Small helper so the chip's text slot doesn't become a nested ternary
// (which the ESLint multiline-ternary rule trips on).
function ChipLabel({
  display,
  placeholder,
}: {
  display: string
  placeholder: string
}) {
  if (display)
    return <span className="max-w-[120px] truncate">{display}</span>
  return <span className="max-w-[120px] truncate">{placeholder}</span>
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
  const Icon = resolveIcon(field)
  const summary = summarizeValue(value)
  const hasValue = summary !== ''

  // 「行业选择」(industry) 业务上目前只支持「爱玛」，其它选项标注「敬请期待」
  const decorateOption = (variable: string, option: string) =>
    variable === 'industry' && option !== '爱玛'
      ? `${option}（敬请期待）`
      : option

  // Display value priority: user-picked > field default > placeholder.
  // The chip always shows something so users see what the field currently
  // resolves to, even before they touch it.
  const displayValue
    = (hasValue ? String(value) : (field.default as string | undefined)) ?? ''
  const decoratedDisplay
    = field.type === InputVarType.select && displayValue
      ? decorateOption(field.variable, displayValue)
      : displayValue

  return (
    <PortalToFollowElem
      open={open}
      onOpenChange={setOpen}
      placement="bottom"
      offset={6}
    >
      <PortalToFollowElemTrigger onClick={() => setOpen(o => !o)}>
        <button
          type="button"
          className={cn(
            'relative flex h-9 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-sm font-medium transition-all active:scale-[0.96]',
            // Required-but-empty fields color the whole chip (icon + text)
            // soft blue so users notice they still need to fill them in.
            field.required && !hasValue
              ? 'border-[#4D80FF]/40 text-[#4D80FF] hover:border-[#4D80FF] hover:bg-[#4D80FF]/5'
              : 'border-[#E9E9EB] text-[#4D4D54] hover:border-[#D1D1D6] hover:bg-[#F4F4F5]',
          )}
          aria-label={field.label}
        >
          <Icon className="h-4 w-4 shrink-0" />
          <ChipLabel
            display={decoratedDisplay}
            placeholder={field.placeholder || field.label}
          />
          {/* Affordance: only select-type chips open a list, so only they
              get a chevron — text/number/paragraph chips open a small
              input panel instead. */}
          {field.type === InputVarType.select && (
            <RiArrowDownSLine className="h-4 w-4 shrink-0 opacity-60" />
          )}
        </button>
      </PortalToFollowElemTrigger>
      <PortalToFollowElemContent className="z-[60]">
        {/* Hard cap height + internal scroll so floating-ui never has to
            flip the popover upward — keeps the chip → popover direction
            consistent regardless of how many select options exist. */}
        <div className="max-h-[220px] w-[280px] overflow-y-auto rounded-xl border border-divider-subtle bg-components-panel-bg p-3 shadow-lg">
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

          {/* Footer is only shown for text-like inputs — select options
              commit on click, so an extra「完成」button there would be
              redundant and confusing. */}
          {isTextLike(field.type) && (
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
          )}
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
