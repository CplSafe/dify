import type {
  DefaultModelResponse,
  Model,
  ModelItem,
  ModelLoadBalancingConfig,
  ModelParameterRule,
  ModelProvider,
  ModelTypeEnum,
} from '@/app/components/header/account-setting/model-provider-page/declarations'
import type {
  UpdateOpenAIKeyResponse,
  ValidateOpenAIKeyResponse,
} from '@/models/app'
import type {
  AccountIntegrate,
  ApiBasedExtension,
  CodeBasedExtension,
  CommonResponse,
  DataSourceNotion,
  FileUploadConfigResponse,
  ICurrentWorkspace,
  InitValidateStatusResponse,
  InvitationResponse,
  IWorkspace,
  LangGeniusVersionResponse,
  Member,
  ModerateResponse,
  OauthResponse,
  PluginProvider,
  Provider,
  ProviderAnthropicToken,
  ProviderAzureToken,
  SetupStatusResponse,
  UserProfileOriginResponse,
} from '@/models/common'
import type { RETRIEVE_METHOD } from '@/types/app'
import { del, get, patch, post, put } from './base'

// ── Shared arg shapes ──────────────────────────────────────────────
type UrlBody<B = Record<string, any>> = { url: string, body: B }
type UrlParams = { url: string, params: Record<string, any> }

// ── Auth ────────────────────────────────────────────────────────────
type LoginSuccess = {
  result: 'success'
  data?: { access_token?: string }
}
type LoginFail = {
  result: 'fail'
  data: string
  code: string
  message: string
}
type LoginResponse = LoginSuccess | LoginFail

export const login = ({ url, body }: UrlBody): Promise<LoginResponse> =>
  post<LoginResponse>(url, { body })

export const webAppLogin = ({ url, body }: UrlBody): Promise<LoginResponse> =>
  post<LoginResponse>(url, { body }, { isPublicAPI: true })

// ── Setup & init ────────────────────────────────────────────────────
export const setup = ({
  body,
}: {
  body: Record<string, any>
}): Promise<CommonResponse> => post<CommonResponse>('/setup', { body })

export const initValidate = ({
  body,
}: {
  body: Record<string, any>
}): Promise<CommonResponse> => post<CommonResponse>('/init', { body })

export const fetchInitValidateStatus
  = (): Promise<InitValidateStatusResponse> =>
    get<InitValidateStatusResponse>('/init')

export const fetchSetupStatus = (): Promise<SetupStatusResponse> =>
  get<SetupStatusResponse>('/setup')

// ── User profile ────────────────────────────────────────────────────
export const fetchUserProfile = ({
  url,
  params,
}: UrlParams): Promise<UserProfileOriginResponse> =>
  get<UserProfileOriginResponse>(url, params, { needAllResponseContent: true })

export const updateUserProfile = ({
  url,
  body,
}: UrlBody): Promise<CommonResponse> => post<CommonResponse>(url, { body })

// ── Version & OAuth ─────────────────────────────────────────────────
export const fetchLangGeniusVersion = ({
  url,
  params,
}: UrlParams): Promise<LangGeniusVersionResponse> =>
  get<LangGeniusVersionResponse>(url, { params })

export const oauth = ({ url, params }: UrlParams): Promise<OauthResponse> =>
  get<OauthResponse>(url, { params })

export const oneMoreStep = ({ url, body }: UrlBody): Promise<CommonResponse> =>
  post<CommonResponse>(url, { body })

// ── Members ─────────────────────────────────────────────────────────
export const fetchMembers = ({
  url,
  params,
}: UrlParams): Promise<{ accounts: Member[] | null }> =>
  get<{ accounts: Member[] | null }>(url, { params })

export const inviteMember = ({
  url,
  body,
}: UrlBody): Promise<InvitationResponse> =>
  post<InvitationResponse>(url, { body })

export const updateMemberRole = ({
  url,
  body,
}: UrlBody): Promise<CommonResponse> => put<CommonResponse>(url, { body })

export const deleteMemberOrCancelInvitation = ({
  url,
}: {
  url: string
}): Promise<CommonResponse> => del<CommonResponse>(url)

export const activateMember = ({
  url,
  body,
}: UrlBody): Promise<LoginResponse> => post<LoginResponse>(url, { body })

// ── Ownership transfer ──────────────────────────────────────────────
type OwnerTransferResponse = CommonResponse & {
  is_valid: boolean
  email: string
  token: string
}

export const sendOwnerEmail = (body: {
  language?: string
}): Promise<CommonResponse & { data: string }> =>
  post<CommonResponse & { data: string }>(
    '/workspaces/current/members/send-owner-transfer-confirm-email',
    { body },
  )

export const verifyOwnerEmail = (body: {
  code: string
  token: string
}): Promise<OwnerTransferResponse> =>
  post<OwnerTransferResponse>(
    '/workspaces/current/members/owner-transfer-check',
    { body },
  )

export const ownershipTransfer = (
  memberID: string,
  body: { token: string },
): Promise<OwnerTransferResponse> =>
  post<OwnerTransferResponse>(
    `/workspaces/current/members/${memberID}/owner-transfer`,
    { body },
  )

// ── Providers (legacy) ──────────────────────────────────────────────
export const fetchProviders = ({
  url,
  params,
}: UrlParams): Promise<Provider[] | null> =>
  get<Provider[] | null>(url, { params })

export const validateProviderKey = ({
  url,
  body,
}: UrlBody<{ token: string }>): Promise<ValidateOpenAIKeyResponse> =>
  post<ValidateOpenAIKeyResponse>(url, { body })

export const updateProviderAIKey = ({
  url,
  body,
}: UrlBody<{
  token: string | ProviderAzureToken | ProviderAnthropicToken
}>): Promise<UpdateOpenAIKeyResponse> =>
  post<UpdateOpenAIKeyResponse>(url, { body })

export const fetchAccountIntegrates = ({
  url,
  params,
}: UrlParams): Promise<{ data: AccountIntegrate[] | null }> =>
  get<{ data: AccountIntegrate[] | null }>(url, { params })

// ── Workspaces ──────────────────────────────────────────────────────
export const fetchCurrentWorkspace = ({
  url,
  params,
}: UrlParams): Promise<ICurrentWorkspace> =>
  post<ICurrentWorkspace>(url, { body: params })

export const updateCurrentWorkspace = ({
  url,
  body,
}: UrlBody): Promise<ICurrentWorkspace> =>
  post<ICurrentWorkspace>(url, { body })

export const fetchWorkspaces = ({
  url,
  params,
}: UrlParams): Promise<{ workspaces: IWorkspace[] }> =>
  get<{ workspaces: IWorkspace[] }>(url, { params })

export const switchWorkspace = ({
  url,
  body,
}: UrlBody): Promise<CommonResponse & { new_tenant: IWorkspace }> =>
  post<CommonResponse & { new_tenant: IWorkspace }>(url, { body })

export const updateWorkspaceInfo = ({
  url,
  body,
}: UrlBody): Promise<ICurrentWorkspace> =>
  post<ICurrentWorkspace>(url, { body })

// ── Data sources ────────────────────────────────────────────────────
export const fetchDataSource = ({
  url,
}: {
  url: string
}): Promise<{ data: DataSourceNotion[] }> =>
  get<{ data: DataSourceNotion[] }>(url)

export const syncDataSourceNotion = ({
  url,
}: {
  url: string
}): Promise<CommonResponse> => get<CommonResponse>(url)

export const updateDataSourceNotionAction = ({
  url,
}: {
  url: string
}): Promise<CommonResponse> => patch<CommonResponse>(url)

export const fetchNotionConnection = (url: string): Promise<{ data: string }> =>
  get<{ data: string }>(url)

export const fetchDataSourceNotionBinding = (
  url: string,
): Promise<{ result: string }> => get<{ result: string }>(url)

// ── Plugin providers ────────────────────────────────────────────────
export const fetchPluginProviders = (
  url: string,
): Promise<PluginProvider[] | null> => get<PluginProvider[] | null>(url)

export const validatePluginProviderKey = ({
  url,
  body,
}: UrlBody<{ credentials: any }>): Promise<ValidateOpenAIKeyResponse> =>
  post<ValidateOpenAIKeyResponse>(url, { body })

export const updatePluginProviderAIKey = ({
  url,
  body,
}: UrlBody<{ credentials: any }>): Promise<UpdateOpenAIKeyResponse> =>
  post<UpdateOpenAIKeyResponse>(url, { body })

// ── Model providers ─────────────────────────────────────────────────
export const fetchModelProviders = (
  url: string,
): Promise<{ data: ModelProvider[] }> => get<{ data: ModelProvider[] }>(url)

export type ModelProviderCredentials = {
  credentials?: Record<string, string | undefined | boolean>
  load_balancing: ModelLoadBalancingConfig
}

export const fetchModelProviderCredentials = (
  url: string,
): Promise<ModelProviderCredentials> => get<ModelProviderCredentials>(url)

export const fetchModelLoadBalancingConfig = (
  url: string,
): Promise<ModelProviderCredentials> => get<ModelProviderCredentials>(url)

export const fetchModelProviderModelList = (
  url: string,
): Promise<{ data: ModelItem[] }> => get<{ data: ModelItem[] }>(url)

export const fetchModelList = (url: string): Promise<{ data: Model[] }> =>
  get<{ data: Model[] }>(url)

export const validateModelProvider = ({
  url,
  body,
}: UrlBody): Promise<ValidateOpenAIKeyResponse> =>
  post<ValidateOpenAIKeyResponse>(url, { body })

export const validateModelLoadBalancingCredentials = ({
  url,
  body,
}: UrlBody): Promise<ValidateOpenAIKeyResponse> =>
  post<ValidateOpenAIKeyResponse>(url, { body })

export const setModelProvider = ({
  url,
  body,
}: UrlBody): Promise<CommonResponse> => post<CommonResponse>(url, { body })

export const deleteModelProvider = ({
  url,
  body,
}: {
  url: string
  body?: any
}): Promise<CommonResponse> => del<CommonResponse>(url, { body })

export const changeModelProviderPriority = ({
  url,
  body,
}: UrlBody): Promise<CommonResponse> => post<CommonResponse>(url, { body })

export const setModelProviderModel = ({
  url,
  body,
}: UrlBody): Promise<CommonResponse> => post<CommonResponse>(url, { body })

export const deleteModelProviderModel = ({
  url,
}: {
  url: string
}): Promise<CommonResponse> => del<CommonResponse>(url)

export const getPayUrl = (url: string): Promise<{ url: string }> =>
  get<{ url: string }>(url)

export const fetchDefaultModal = (
  url: string,
): Promise<{ data: DefaultModelResponse }> =>
  get<{ data: DefaultModelResponse }>(url)

export const updateDefaultModel = ({
  url,
  body,
}: UrlBody): Promise<CommonResponse> => post<CommonResponse>(url, { body })

export const fetchModelParameterRules = (
  url: string,
): Promise<{ data: ModelParameterRule[] }> =>
  get<{ data: ModelParameterRule[] }>(url)

export const enableModel = (
  url: string,
  body: { model: string, model_type: ModelTypeEnum },
): Promise<CommonResponse> => patch<CommonResponse>(url, { body })

export const disableModel = (
  url: string,
  body: { model: string, model_type: ModelTypeEnum },
): Promise<CommonResponse> => patch<CommonResponse>(url, { body })

// ── Files ───────────────────────────────────────────────────────────
export const fetchFilePreview = ({
  fileID,
}: {
  fileID: string
}): Promise<{ content: string }> =>
  get<{ content: string }>(`/files/${fileID}/preview`)

export const fetchFileUploadConfig = ({
  url,
}: {
  url: string
}): Promise<FileUploadConfigResponse> => get<FileUploadConfigResponse>(url)

type RemoteFileInfo = {
  id: string
  name: string
  size: number
  mime_type: string
  url: string
}

export const uploadRemoteFileInfo = (
  url: string,
  isPublic?: boolean,
  silent?: boolean,
): Promise<RemoteFileInfo> =>
  post<RemoteFileInfo>(
    '/remote-files/upload',
    { body: { url } },
    { isPublicAPI: isPublic, silent },
  )

// ── Invitation ──────────────────────────────────────────────────────
type InvitationCheckResponse = CommonResponse & {
  is_valid: boolean
  data: { workspace_name: string, email: string, workspace_id: string }
}

export const invitationCheck = ({
  url,
  params,
}: {
  url: string
  params: { workspace_id?: string, email?: string, token: string }
}): Promise<InvitationCheckResponse> =>
  get<InvitationCheckResponse>(url, { params })

// ── Extensions ──────────────────────────────────────────────────────
export const fetchApiBasedExtensionList = (
  url: string,
): Promise<ApiBasedExtension[]> => get<ApiBasedExtension[]>(url)

export const fetchApiBasedExtensionDetail = (
  url: string,
): Promise<ApiBasedExtension> => get<ApiBasedExtension>(url)

export const addApiBasedExtension = ({
  url,
  body,
}: UrlBody<ApiBasedExtension>): Promise<ApiBasedExtension> =>
  post<ApiBasedExtension>(url, { body })

export const updateApiBasedExtension = ({
  url,
  body,
}: UrlBody<ApiBasedExtension>): Promise<ApiBasedExtension> =>
  post<ApiBasedExtension>(url, { body })

export const deleteApiBasedExtension = (
  url: string,
): Promise<{ result: string }> => del<{ result: string }>(url)

export const fetchCodeBasedExtensionList = (
  url: string,
): Promise<CodeBasedExtension> => get<CodeBasedExtension>(url)

// ── Moderation & retrieval ──────────────────────────────────────────
export const moderate = (
  url: string,
  body: { app_id: string, text: string },
): Promise<ModerateResponse> => post<ModerateResponse>(url, { body })

type RetrievalMethodsRes = { retrieval_method: RETRIEVE_METHOD[] }

export const fetchSupportRetrievalMethods = (
  url: string,
): Promise<RetrievalMethodsRes> => get<RetrievalMethodsRes>(url)

// ── Console password reset ──────────────────────────────────────────
type ForgotPasswordResponse = CommonResponse & { data: string }
type VerifyTokenResponse = CommonResponse & {
  is_valid: boolean
  email: string
}

export const sendForgotPasswordEmail = ({
  url,
  body,
}: UrlBody<{ email: string }>): Promise<ForgotPasswordResponse> =>
  post<ForgotPasswordResponse>(url, { body })

export const verifyForgotPasswordToken = ({
  url,
  body,
}: UrlBody<{ token: string }>): Promise<VerifyTokenResponse> =>
  post<VerifyTokenResponse>(url, { body })

export const changePasswordWithToken = ({
  url,
  body,
}: UrlBody<{
  token: string
  new_password: string
  password_confirm: string
}>): Promise<CommonResponse> => post<CommonResponse>(url, { body })

// ── WebApp password reset ───────────────────────────────────────────
export const sendWebAppForgotPasswordEmail = ({
  url,
  body,
}: UrlBody<{ email: string }>): Promise<ForgotPasswordResponse> =>
  post<ForgotPasswordResponse>(url, { body }, { isPublicAPI: true })

export const verifyWebAppForgotPasswordToken = ({
  url,
  body,
}: UrlBody<{ token: string }>): Promise<VerifyTokenResponse> =>
  post<VerifyTokenResponse>(url, { body }, { isPublicAPI: true })

export const changeWebAppPasswordWithToken = ({
  url,
  body,
}: UrlBody<{
  token: string
  new_password: string
  password_confirm: string
}>): Promise<CommonResponse> =>
  post<CommonResponse>(url, { body }, { isPublicAPI: true })

// ── Console email login & reset ─────────────────────────────────────
type CodeResponse = CommonResponse & { data: string }
type ResetCodeResponse = CommonResponse & {
  data: string
  message?: string
  code?: string
}
type VerifyResetResponse = CommonResponse & {
  is_valid: boolean
  token: string
}

export const sendEMailLoginCode = (
  email: string,
  language = 'en-US',
): Promise<CodeResponse> =>
  post<CodeResponse>('/email-code-login', { body: { email, language } })

export const emailLoginWithCode = (data: {
  email: string
  code: string
  token: string
  language: string
}): Promise<LoginResponse> =>
  post<LoginResponse>('/email-code-login/validity', { body: data })

export const sendResetPasswordCode = (
  email: string,
  language = 'en-US',
): Promise<ResetCodeResponse> =>
  post<ResetCodeResponse>('/forgot-password', { body: { email, language } })

export const verifyResetPasswordCode = (body: {
  email: string
  code: string
  token: string
}): Promise<VerifyResetResponse> =>
  post<VerifyResetResponse>('/forgot-password/validity', { body })

// ── WebApp email login & reset ──────────────────────────────────────
export const sendWebAppEMailLoginCode = (
  email: string,
  language = 'en-US',
): Promise<CodeResponse> =>
  post<CodeResponse>(
    '/email-code-login',
    { body: { email, language } },
    { isPublicAPI: true },
  )

export const webAppEmailLoginWithCode = (data: {
  email: string
  code: string
  token: string
}): Promise<LoginResponse> =>
  post<LoginResponse>(
    '/email-code-login/validity',
    { body: data },
    { isPublicAPI: true },
  )

export const sendWebAppResetPasswordCode = (
  email: string,
  language = 'en-US',
): Promise<ResetCodeResponse> =>
  post<ResetCodeResponse>(
    '/forgot-password',
    { body: { email, language } },
    { isPublicAPI: true },
  )

export const verifyWebAppResetPasswordCode = (body: {
  email: string
  code: string
  token: string
}): Promise<VerifyResetResponse> =>
  post<VerifyResetResponse>(
    '/forgot-password/validity',
    { body },
    { isPublicAPI: true },
  )

// ── SMS login ───────────────────────────────────────────────────────
export const sendSmsLoginCode = (phone: string): Promise<CommonResponse> =>
  post<CommonResponse>('/sms-login/send-code', { body: { phone } })

export const smsLoginVerify = (data: {
  phone: string
  code: string
  invite_token?: string
}): Promise<CommonResponse> =>
  post<CommonResponse>('/sms-login/verify', { body: data })

// ── Account management ──────────────────────────────────────────────
export const sendDeleteAccountCode = (): Promise<
  CommonResponse & { data: string }
> => get<CommonResponse & { data: string }>('/account/delete/verify')

export const verifyDeleteAccountCode = (body: {
  code: string
  token: string
}): Promise<CommonResponse & { is_valid: boolean }> =>
  post<CommonResponse & { is_valid: boolean }>('/account/delete', { body })

export const submitDeleteAccountFeedback = (body: {
  feedback: string
  email: string
}): Promise<CommonResponse> =>
  post<CommonResponse>('/account/delete/feedback', { body })

export const getDocDownloadUrl = (doc_name: string): Promise<{ url: string }> =>
  get<{ url: string }>(
    '/compliance/download',
    { params: { doc_name } },
    { silent: true },
  )

export const sendVerifyCode = (body: {
  email: string
  phase: string
  token?: string
}): Promise<CommonResponse & { data: string }> =>
  post<CommonResponse & { data: string }>('/account/change-email', { body })

export const verifyEmail = (body: {
  email: string
  code: string
  token: string
}): Promise<
  CommonResponse & { is_valid: boolean, email: string, token: string }
> =>
  post<CommonResponse & { is_valid: boolean, email: string, token: string }>(
    '/account/change-email/validity',
    { body },
  )

export const resetEmail = (body: {
  new_email: string
  token: string
}): Promise<CommonResponse> =>
  post<CommonResponse>('/account/change-email/reset', { body })

export const checkEmailExisted = (body: {
  email: string
}): Promise<CommonResponse> =>
  post<CommonResponse>(
    '/account/change-email/check-email-unique',
    { body },
    { silent: true },
  )
