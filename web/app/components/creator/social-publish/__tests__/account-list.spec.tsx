import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as React from 'react'

import { SocialPublishAccountList } from '../account-list'

const {
  fetchSocialPublishAccounts,
  deleteSocialPublishAccount,
  startSocialPublishAuth,
  fetchSocialPublishAuthStatus,
} = vi.hoisted(() => ({
  fetchSocialPublishAccounts: vi.fn(),
  deleteSocialPublishAccount: vi.fn(),
  startSocialPublishAuth: vi.fn(),
  fetchSocialPublishAuthStatus: vi.fn(),
}))

vi.mock('@/service/social-publish', () => ({
  fetchSocialPublishAccounts,
  deleteSocialPublishAccount,
  startSocialPublishAuth,
  fetchSocialPublishAuthStatus,
}))

const STABLE_T_RESULT = { t: (key: string) => key }
vi.mock('react-i18next', () => ({
  useTranslation: () => STABLE_T_RESULT,
}))

const toastSpies = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('@/app/components/base/ui/toast', () => ({
  toast: { success: toastSpies.success, error: toastSpies.error },
}))

const account = (overrides: Record<string, unknown> = {}) => ({
  id: 'row-1',
  platform: 'douyin',
  display_name: '小妹',
  avatar_url: null,
  status: 'active',
  last_check_at: null,
  created_at: '2026-04-18T00:00:00',
  ...overrides,
})

beforeEach(() => {
  fetchSocialPublishAccounts.mockReset()
  deleteSocialPublishAccount.mockReset()
  startSocialPublishAuth.mockReset()
  fetchSocialPublishAuthStatus.mockReset()
  toastSpies.success.mockClear()
  toastSpies.error.mockClear()
})

describe('SocialPublishAccountList', () => {
  it('renders an empty state when the list is empty', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [] })

    render(<SocialPublishAccountList />)

    expect(await screen.findByText('accountList.empty.title')).toBeInTheDocument()
    expect(screen.getByText('accountList.addDouyinAccount')).toBeInTheDocument()
  })

  it('renders a list when accounts are returned', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({
      data: [account(), account({ id: 'row-2', display_name: '小红', status: 'expired' })],
    })

    render(<SocialPublishAccountList />)

    await waitFor(() => expect(screen.getByText('小妹')).toBeInTheDocument())
    expect(screen.getByText('小红')).toBeInTheDocument()
    // expired row gets the re-auth button.
    expect(screen.getByText('accountList.actions.reauth')).toBeInTheDocument()
  })

  it('renders the disabled-feature state and hides Add when feature_disabled', async () => {
    fetchSocialPublishAccounts.mockRejectedValue({ code: 'feature_disabled' })

    render(<SocialPublishAccountList />)

    expect(await screen.findByText('auth.errors.feature_disabled')).toBeInTheDocument()
    expect(screen.queryByText('accountList.addDouyinAccount')).not.toBeInTheDocument()
  })

  it('renders an error banner with the localized code for non-feature errors', async () => {
    fetchSocialPublishAccounts.mockRejectedValue({ code: 'sau_unreachable' })

    render(<SocialPublishAccountList />)

    expect(await screen.findByText('auth.errors.sau_unreachable')).toBeInTheDocument()
    // Add button still visible (not a config-disabled state).
    expect(screen.getByText('accountList.addDouyinAccount')).toBeInTheDocument()
  })

  it('falls back to the unknown error key when the rejection has no code', async () => {
    fetchSocialPublishAccounts.mockRejectedValue(new Error('boom'))

    render(<SocialPublishAccountList />)

    expect(await screen.findByText('auth.errors.unknown')).toBeInTheDocument()
  })

  it('opens the QR modal when Add is clicked', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [] })
    // Modal calls start_auth on open — keep it pending so we just verify
    // that the modal opened.
    startSocialPublishAuth.mockReturnValue(new Promise(() => {}))

    render(<SocialPublishAccountList />)

    fireEvent.click(await screen.findByText('accountList.addDouyinAccount'))
    expect(await screen.findByText('auth.modalTitle')).toBeInTheDocument()
  })

  it('delete flow: opens confirm, calls service on confirm, toasts success and reloads', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [account()] })
    deleteSocialPublishAccount.mockResolvedValue({ result: 'success' })

    render(<SocialPublishAccountList />)

    await waitFor(() => expect(screen.getByText('小妹')).toBeInTheDocument())

    // The trash button has no visible text — find via the destructive ghost
    // button next to the row. We rely on there being exactly one such row.
    const buttons = screen.getAllByRole('button')
    const deleteBtn = buttons.find(b => b.querySelector('svg') && !b.textContent?.trim())
    expect(deleteBtn).toBeDefined()
    fireEvent.click(deleteBtn!)

    fireEvent.click(await screen.findByText('accountList.deleteConfirm.confirm'))

    await waitFor(() =>
      expect(deleteSocialPublishAccount).toHaveBeenCalledWith('row-1'),
    )
    await waitFor(() =>
      expect(toastSpies.success).toHaveBeenCalledWith('accountList.deleteConfirm.success'),
    )
    // List was reloaded after the success.
    expect(fetchSocialPublishAccounts).toHaveBeenCalledTimes(2)
  })

  it('delete flow: surfaces the localized error code on failure', async () => {
    fetchSocialPublishAccounts.mockResolvedValue({ data: [account()] })
    deleteSocialPublishAccount.mockRejectedValue({ code: 'tenant_mismatch' })

    render(<SocialPublishAccountList />)

    await waitFor(() => expect(screen.getByText('小妹')).toBeInTheDocument())
    const buttons = screen.getAllByRole('button')
    const deleteBtn = buttons.find(b => b.querySelector('svg') && !b.textContent?.trim())
    fireEvent.click(deleteBtn!)
    fireEvent.click(await screen.findByText('accountList.deleteConfirm.confirm'))

    await waitFor(() =>
      expect(toastSpies.error).toHaveBeenCalledWith('auth.errors.tenant_mismatch'),
    )
  })
})
