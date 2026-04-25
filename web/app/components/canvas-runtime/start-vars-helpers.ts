import type { UserInputFormItem } from '@/types/app'

export type StartVarValues = Record<string, string>

const FIELD_KEYS = ['text-input', 'paragraph', 'select'] as const

type FieldShape = { variable: string, default?: string }

const extractField = (raw: UserInputFormItem): FieldShape | undefined => {
  const item = raw as Record<string, FieldShape | undefined>
  return FIELD_KEYS.map(key => item[key]).find(Boolean)
}

export const buildDefaultStartVars = (
  form: UserInputFormItem[] | null | undefined,
): StartVarValues =>
  (form ?? []).reduce<StartVarValues>((values, raw) => {
    const field = extractField(raw)
    if (field?.default)
      values[field.variable] = field.default
    return values
  }, {})
