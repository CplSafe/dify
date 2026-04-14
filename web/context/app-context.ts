'use client'

import type {
  ICurrentWorkspace,
  LangGeniusVersionResponse,
  UserProfileResponse,
} from '@/models/common'
import { noop } from 'es-toolkit/function'
import {
  createContext,
  useContext,
  useContextSelector,
} from 'use-context-selector'

// useSelector is a forward reference — declare its type first so AppContextValue can reference it.
// The actual implementation is defined after AppContextValue and AppContext below.
type SelectorFn = <T>(selector: (value: AppContextValue) => T) => T

export type AppContextValue = {
  userProfile: UserProfileResponse
  mutateUserProfile: VoidFunction
  currentWorkspace: ICurrentWorkspace
  isCurrentWorkspaceManager: boolean
  isCurrentWorkspaceOwner: boolean
  isCurrentWorkspaceEditor: boolean
  isCurrentWorkspaceDatasetOperator: boolean
  isSystemAdmin: boolean
  mutateCurrentWorkspace: VoidFunction
  langGeniusVersionInfo: LangGeniusVersionResponse
  useSelector: SelectorFn
  isLoadingCurrentWorkspace: boolean
  isValidatingCurrentWorkspace: boolean
}

export const userProfilePlaceholder: UserProfileResponse = {
  id: '',
  name: '',
  email: '',
  avatar: '',
  avatar_url: '',
  is_password_set: false,
}

export const initialLangGeniusVersionInfo: LangGeniusVersionResponse = {
  current_env: '',
  current_version: '',
  latest_version: '',
  release_date: '',
  release_notes: '',
  version: '',
  can_auto_update: false,
}

export const initialWorkspaceInfo: ICurrentWorkspace = {
  id: '',
  name: '',
  plan: '',
  status: '',
  created_at: 0,
  role: 'normal',
  providers: [],
  trial_credits: 200,
  trial_credits_used: 0,
  next_credit_reset_date: 0,
}

export const AppContext = createContext<AppContextValue>({
  userProfile: userProfilePlaceholder,
  currentWorkspace: initialWorkspaceInfo,
  isCurrentWorkspaceManager: false,
  isCurrentWorkspaceOwner: false,
  isCurrentWorkspaceEditor: false,
  isCurrentWorkspaceDatasetOperator: false,
  isSystemAdmin: false,
  mutateUserProfile: noop,
  mutateCurrentWorkspace: noop,
  langGeniusVersionInfo: initialLangGeniusVersionInfo,
  useSelector,
  isLoadingCurrentWorkspace: false,
  isValidatingCurrentWorkspace: false,
})

export function useSelector<T>(selector: (value: AppContextValue) => T): T {
  return useContextSelector(AppContext, selector)
}

export const useAppContext = () => useContext(AppContext)
