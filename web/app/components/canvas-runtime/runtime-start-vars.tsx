'use client'

import type { FC } from 'react'
import type { StartVarValues } from './start-vars-helpers'
import type { UserInputFormItem } from '@/types/app'
import { useMemo } from 'react'
import { cn } from '@/utils/classnames'

/**
 * Renders the chatflow's start-node user_input_form as a compact set
 * of inline fields above the bottom input dock.
 *
 * Why this exists: the chatflow start node can declare required vars
 * (industry, ratio, …); without them the engine rejects the run with
 * "<var> is required in input form". The canvas-runtime page reads the
 * form spec from /installed-apps/<id>/parameters and hands it here.
 *
 * Behaviour:
 * - Hidden when there are no fields.
 * - Pure controlled: parent owns the values map.
 * - text-input / paragraph render as inputs; select renders as a
 *   native <select>. Defaults from the form spec seed the initial
 *   values.
 */

type RuntimeStartVarsProps = {
  form: UserInputFormItem[] | null | undefined
  values: StartVarValues
  onChange: (next: StartVarValues) => void
}

type NormalizedField = {
  variable: string
  label: string
  required: boolean
  hide: boolean
  kind: 'text' | 'paragraph' | 'select'
  options?: string[]
  maxLength?: number
}

const _normalize = (
  form: UserInputFormItem[] | null | undefined,
): NormalizedField[] => {
  if (!form?.length)
    return []
  const out: NormalizedField[] = []
  for (const raw of form) {
    if ('text-input' in raw) {
      const f = raw['text-input']
      out.push({
        variable: f.variable,
        label: f.label || f.variable,
        required: !!f.required,
        hide: !!f.hide,
        kind: 'text',
        maxLength: f.max_length,
      })
    }
    else if ('paragraph' in raw) {
      const f = raw.paragraph
      out.push({
        variable: f.variable,
        label: f.label || f.variable,
        required: !!f.required,
        hide: !!f.hide,
        kind: 'paragraph',
        maxLength: f.max_length,
      })
    }
    else if ('select' in raw) {
      const f = raw.select
      out.push({
        variable: f.variable,
        label: f.label || f.variable,
        required: !!f.required,
        hide: !!f.hide,
        kind: 'select',
        options: f.options,
      })
    }
  }
  return out.filter(f => !f.hide)
}

const RuntimeStartVars: FC<RuntimeStartVarsProps> = ({
  form,
  values,
  onChange,
}) => {
  const fields = useMemo(() => _normalize(form), [form])
  if (fields.length === 0)
    return null

  const setField = (variable: string, next: string) => {
    onChange({ ...values, [variable]: next })
  }

  return (
    <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
      {fields.map((f) => {
        const value = values[f.variable] ?? ''
        const baseInputCls = cn(
          'border-components-input-border bg-components-input-bg w-full rounded-lg border px-2 py-1.5 system-sm-regular text-text-primary outline-hidden',
          'focus:border-components-input-border-hover',
        )
        return (
          <label key={f.variable} className="flex flex-col gap-1">
            <span className="system-2xs-medium-uppercase text-text-tertiary">
              {f.label}
              {f.required && (
                <span className="ml-1 text-text-destructive">*</span>
              )}
            </span>
            {f.kind === 'select'
              ? (
                  <select
                    value={value}
                    onChange={e => setField(f.variable, e.target.value)}
                    className={baseInputCls}
                  >
                    <option value="">请选择…</option>
                    {(f.options ?? []).map(opt => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                )
              : f.kind === 'paragraph'
                ? (
                    <textarea
                      value={value}
                      onChange={e => setField(f.variable, e.target.value)}
                      maxLength={f.maxLength}
                      rows={2}
                      className={cn(baseInputCls, 'resize-none')}
                    />
                  )
                : (
                    <input
                      type="text"
                      value={value}
                      onChange={e => setField(f.variable, e.target.value)}
                      maxLength={f.maxLength}
                      className={baseInputCls}
                    />
                  )}
          </label>
        )
      })}
    </div>
  )
}

export default RuntimeStartVars
