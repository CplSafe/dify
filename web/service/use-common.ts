import type { FileTypesRes } from './datasets'
import type {
  Model,
  ModelParameterRule,
  ModelProvider,
  ModelTypeEnum,
} from '@/app/components/header/account-setting/model-provider-page/declarations'
import type {
  AccountIntegrate,
  ApiBasedExtension,
  CodeBasedExtension,
  CommonResponse,
  FileUploadConfigResponse,
  ICurrentWorkspace,
  IWorkspace,
  LangGeniusVersionResponse,
  Member,
  PluginProvider,
  StructuredOutputRulesRequestBody,
  StructuredOutputRulesResponse,
  UserProfileResponse,
} from '@/models/common'
import type { RETRIEVE_METHOD } from '@/types/app'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IS_DEV } from '@/config'
import { get, post } from './base'

const NAME_SPACE = 'common'

// Small helper to keep queryKey tuples readable while preserving the exact
// `[NAME_SPACE, ...rest] as const` shape consumers expect.
const key = <const T extends readonly unknown[]>(...parts: T) =>
  [NAME_SPACE, ...parts] as const

export const commonQueryKeys = {
  fileUploadConfig: key('file-upload-config'),
  userProfile: key('user-profile'),
  currentWorkspace: key('current-workspace'),
  workspaces: key('workspaces'),
  members: key('members'),
  filePreview: (fileID: string) => key('file-preview', fileID),
  schemaDefinitions: key('schema-type-definitions'),
  isLogin: key('is-login'),
  modelProviders: key('model-providers'),
  modelList: (type: ModelTypeEnum) => key('model-list', type),
  defaultModel: (type: ModelTypeEnum) => key('default-model', type),
  retrievalMethods: key('support-retrieval-methods'),
  accountIntegrates: key('account-integrates'),
  pluginProviders: key('plugin-providers'),
  notionConnection: key('notion-connection'),
  apiBasedExtensions: key('api-based-extensions'),
  codeBasedExtensions: (module?: string) =>
    key('code-based-extensions', module),
  invitationCheck: (params?: {
    workspace_id?: string
    email?: string
    token?: string
  }) =>
    key(
      'invitation-check',
      params?.workspace_id ?? '',
      params?.email ?? '',
      params?.token ?? '',
    ),
  notionBinding: (code?: string | null) => key('notion-binding', code),
  modelParameterRules: (provider?: string, model?: string) =>
    key('model-parameter-rules', provider, model),
  langGeniusVersion: (currentVersion?: string | null) =>
    key('langgenius-version', currentVersion),
  forgotPasswordValidity: (token?: string | null) =>
    key('forgot-password-validity', token),
  dataSourceIntegrates: key('data-source-integrates'),
}

// Thin wrapper for the common `post` mutation shape: fixed URL + JSON body.
const usePostMutation = <TResponse, TBody = void>(name: string, url: string) =>
  useMutation({
    mutationKey: [NAME_SPACE, name],
    mutationFn: (body: TBody) =>
      post<TResponse>(url, { body: body as Record<string, unknown> }),
  })

export const useFileUploadConfig = () =>
  useQuery<FileUploadConfigResponse>({
    queryKey: commonQueryKeys.fileUploadConfig,
    queryFn: () => get<FileUploadConfigResponse>('/files/upload'),
  })

type UserProfileWithMeta = {
  profile: UserProfileResponse
  meta: {
    currentVersion: string | null
    currentEnv: string | null
  }
}

export const useUserProfile = () => {
  return useQuery<UserProfileWithMeta>({
    queryKey: commonQueryKeys.userProfile,
    queryFn: async () => {
      const response = (await get<Response>(
        '/account/profile',
        {},
        { needAllResponseContent: true },
      )) as Response
      const profile = (await response.clone().json()) as UserProfileResponse
      return {
        profile,
        meta: {
          currentVersion: response.headers.get('x-version'),
          currentEnv: IS_DEV ? 'DEVELOPMENT' : response.headers.get('x-env'),
        },
      }
    },
    staleTime: 0,
    gcTime: 0,
  })
}

export const useLangGeniusVersion = (
  currentVersion?: string | null,
  enabled?: boolean,
) =>
  useQuery<LangGeniusVersionResponse>({
    queryKey: commonQueryKeys.langGeniusVersion(currentVersion || undefined),
    queryFn: () =>
      get<LangGeniusVersionResponse>('/version', {
        params: { current_version: currentVersion },
      }),
    enabled: !!currentVersion && (enabled ?? true),
  })

export const useCurrentWorkspace = () =>
  useQuery<ICurrentWorkspace>({
    queryKey: commonQueryKeys.currentWorkspace,
    queryFn: () => post<ICurrentWorkspace>('/workspaces/current'),
  })

export const useWorkspaces = () =>
  useQuery<{ workspaces: IWorkspace[] }>({
    queryKey: commonQueryKeys.workspaces,
    queryFn: () => get<{ workspaces: IWorkspace[] }>('/workspaces'),
  })

export const useGenerateStructuredOutputRules = () =>
  usePostMutation<
    StructuredOutputRulesResponse,
    StructuredOutputRulesRequestBody
  >('generate-structured-output-rules', '/rule-structured-output-generate')

export type MailSendResponse = { data: string, result: string }
export const useSendMail = () =>
  usePostMutation<MailSendResponse, { email: string, language: string }>(
    'mail-send',
    '/email-register/send-email',
  )

export type MailValidityResponse = { is_valid: boolean, token: string }

export const useMailValidity = () =>
  usePostMutation<
    MailValidityResponse,
    { email: string, code: string, token: string }
  >('mail-validity', '/email-register/validity')

export type MailRegisterResponse = { result: string, data: {} }

// Optional invite_code is captured from ?invite_code= in the signup URL.
// The backend binds transactionally during registration — a post-register
// POST /creator/invitations/bind used to silently 401 because no auth
// cookie exists on the fresh account yet.
type MailRegisterPayload = {
  token: string
  new_password: string
  password_confirm: string
  invite_code?: string
}

export const useMailRegister = () =>
  usePostMutation<MailRegisterResponse, MailRegisterPayload>(
    'mail-register',
    '/email-register',
  )

export const useFileSupportTypes = () =>
  useQuery<FileTypesRes>({
    queryKey: [NAME_SPACE, 'file-types'],
    queryFn: () => get<FileTypesRes>('/files/support-type'),
  })

type MemberResponse = {
  accounts: Member[] | null
}

export const useMembers = () =>
  useQuery<MemberResponse>({
    queryKey: commonQueryKeys.members,
    queryFn: () =>
      get<MemberResponse>('/workspaces/current/members', { params: {} }),
  })

type FilePreviewResponse = {
  content: string
}

export const useFilePreview = (fileID: string) =>
  useQuery<FilePreviewResponse>({
    queryKey: commonQueryKeys.filePreview(fileID),
    queryFn: () => get<FilePreviewResponse>(`/files/${fileID}/preview`),
    enabled: !!fileID,
  })

export type SchemaTypeDefinition = {
  name: string
  schema: {
    properties: Record<string, unknown>
  }
}

export const useSchemaTypeDefinitions = () =>
  useQuery<SchemaTypeDefinition[]>({
    queryKey: commonQueryKeys.schemaDefinitions,
    queryFn: () => get<SchemaTypeDefinition[]>('/spec/schema-definitions'),
  })

type isLogin = {
  logged_in: boolean
}

export const useIsLogin = () =>
  useQuery<isLogin>({
    queryKey: commonQueryKeys.isLogin,
    staleTime: 0,
    gcTime: 0,
    queryFn: async (): Promise<isLogin> => {
      try {
        await get('/account/profile', {}, { silent: true })
        return { logged_in: true }
      }
      catch {
        // Any error (401, 500, network error, etc.) means not logged in
        return { logged_in: false }
      }
    },
  })

export const useLogout = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: [NAME_SPACE, 'logout'],
    mutationFn: () => post('/logout'),
    // Wipe every cached query on logout so the next sign-in doesn't paint
    // the previous account's user profile / workspace / balance for a frame
    // before re-fetching. TanStack Query's global cache is keyed only by
    // query name (no account_id), so without this the next mount returns
    // stale data first and revalidates — the user sees the old account's
    // name and balance flash for a moment after switching accounts.
    // Run on settled (success or error): a failed network logout still
    // clears the local session token, so we must clear cache to match.
    onSettled: () => {
      queryClient.clear()
    },
  })
}

type ForgotPasswordValidity = CommonResponse & {
  is_valid: boolean
  email: string
}
export const useVerifyForgotPasswordToken = (token?: string | null) =>
  useQuery<ForgotPasswordValidity>({
    queryKey: commonQueryKeys.forgotPasswordValidity(token),
    queryFn: () =>
      post<ForgotPasswordValidity>('/forgot-password/validity', {
        body: { token },
      }),
    enabled: !!token,
    staleTime: 0,
    gcTime: 0,
    retry: false,
  })

type OneMoreStepPayload = {
  invitation_code: string
  interface_language: string
  timezone: string
}
export const useOneMoreStep = () =>
  usePostMutation<CommonResponse, OneMoreStepPayload>(
    'one-more-step',
    '/account/init',
  )

export const useModelProviders = () =>
  useQuery<{ data: ModelProvider[] }>({
    queryKey: commonQueryKeys.modelProviders,
    queryFn: () =>
      get<{ data: ModelProvider[] }>('/workspaces/current/model-providers'),
  })

export const useModelListByType = (type: ModelTypeEnum, enabled = true) =>
  useQuery<{ data: Model[] }>({
    queryKey: commonQueryKeys.modelList(type),
    queryFn: () =>
      get<{ data: Model[] }>(`/workspaces/current/models/model-types/${type}`),
    enabled,
  })

export const useSupportRetrievalMethods = () =>
  useQuery<{ retrieval_method: RETRIEVE_METHOD[] }>({
    queryKey: commonQueryKeys.retrievalMethods,
    queryFn: () =>
      get<{ retrieval_method: RETRIEVE_METHOD[] }>(
        '/datasets/retrieval-setting',
      ),
  })

export const useAccountIntegrates = () =>
  useQuery<{ data: AccountIntegrate[] | null }>({
    queryKey: commonQueryKeys.accountIntegrates,
    queryFn: () =>
      get<{ data: AccountIntegrate[] | null }>('/account/integrates'),
  })

export const usePluginProviders = () =>
  useQuery<PluginProvider[] | null>({
    queryKey: commonQueryKeys.pluginProviders,
    queryFn: () =>
      get<PluginProvider[] | null>('/workspaces/current/tool-providers'),
  })

export const useCodeBasedExtensions = (module: string) =>
  useQuery<CodeBasedExtension>({
    queryKey: commonQueryKeys.codeBasedExtensions(module),
    queryFn: () =>
      get<CodeBasedExtension>(`/code-based-extension?module=${module}`),
  })

export const useApiBasedExtensions = () =>
  useQuery<ApiBasedExtension[]>({
    queryKey: commonQueryKeys.apiBasedExtensions,
    queryFn: () => get<ApiBasedExtension[]>('/api-based-extension'),
  })

export const useInvitationCheck = (
  params?: { workspace_id?: string, email?: string, token?: string },
  enabled?: boolean,
) =>
  useQuery({
    queryKey: commonQueryKeys.invitationCheck(params),
    queryFn: () =>
      get<{
        is_valid: boolean
        data: { workspace_name: string, email: string, workspace_id: string }
        result: string
      }>('/activate/check', { params }),
    enabled: enabled ?? !!params?.token,
    retry: false,
  })

export const useNotionBinding = (code?: string | null, enabled?: boolean) =>
  useQuery({
    queryKey: commonQueryKeys.notionBinding(code),
    queryFn: () =>
      get<{ result: string }>('/oauth/data-source/binding/notion', {
        params: { code },
      }),
    enabled: !!code && (enabled ?? true),
  })

export const useModelParameterRules = (
  provider?: string,
  model?: string,
  enabled?: boolean,
) =>
  useQuery<{ data: ModelParameterRule[] }>({
    queryKey: commonQueryKeys.modelParameterRules(provider, model),
    queryFn: () =>
      get<{ data: ModelParameterRule[] }>(
        `/workspaces/current/model-providers/${provider}/models/parameter-rules`,
        { params: { model }, silent: true },
      ),
    enabled: !!provider && !!model && (enabled ?? true),
  })
