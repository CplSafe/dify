export const ACCOUNT_SETTING_MODAL_ACTION = 'showSettings'

export const ACCOUNT_SETTING_TAB = {
  PROVIDER: 'provider',
  MEMBERS: 'members',
  SOCIAL_PUBLISH: 'social-publish',
  BILLING: 'billing',
  DATA_SOURCE: 'data-source',
  API_BASED_EXTENSION: 'api-based-extension',
  CUSTOM: 'custom',
  LANGUAGE: 'language',
  USER_MANAGEMENT: 'user-management',
  REBATE_CONFIG: 'rebate-config',
  SMS_LOGS: 'sms-logs',
} as const

export type AccountSettingTab
  = (typeof ACCOUNT_SETTING_TAB)[keyof typeof ACCOUNT_SETTING_TAB]

export const DEFAULT_ACCOUNT_SETTING_TAB = ACCOUNT_SETTING_TAB.MEMBERS

export const isValidAccountSettingTab = (
  tab: string | null,
): tab is AccountSettingTab => {
  if (!tab)
    return false
  return Object.values(ACCOUNT_SETTING_TAB).includes(tab as AccountSettingTab)
}
