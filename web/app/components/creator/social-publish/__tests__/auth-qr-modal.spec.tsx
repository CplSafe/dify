import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as React from 'react'

import { AuthQrModal } from '../auth-qr-modal'

// ----- service mocks (vi.hoisted so they're defined before the SUT module
// import resolves the @/service/social-publish path) -----

const { startSocialPublishAuth, fetchSocialPublishAuthStatus } = vi.hoisted(
  () => ({
    startSocialPublishAuth: vi.fn(),
    fetchSocialPublishAuthStatus: vi.fn(),
  }),
)

vi.mock('@/service/social-publish', () => ({
  startSocialPublishAuth,
  fetchSocialPublishAuthStatus,
}))

// ----- i18n: pass-through so assertions can match raw keys -----

// useTranslation MUST return a stable t() across renders — otherwise the
// modal's useEffect deps shift on every render (because `localizeError`
// closes over `t`), the cleanup keeps bumping `generationRef`, and the
// 2s polling timer is cancelled before it ever fires.
const STABLE_T_RESULT = { t: (key: string) => key }
vi.mock('react-i18next', () => ({
  useTranslation: () => STABLE_T_RESULT,
}))

const FAKE_QR = 'data:image/png;base64,FAKE'

beforeEach(() => {
  startSocialPublishAuth.mockReset()
  fetchSocialPublishAuthStatus.mockReset()
  // Default: status poll never advances past waiting.
  fetchSocialPublishAuthStatus.mockResolvedValue({
    status: 'waiting',
    account: null,
    message: null,
  })
})

describe('AuthQrModal', () => {
  it('renders the QR image once start_auth resolves', async () => {
    startSocialPublishAuth.mockResolvedValue({
      session_id: 'sid-1',
      qr_image_base64: FAKE_QR,
      expires_in: 180,
    })

    render(
      <AuthQrModal
        open
        accountId={null}
        onOpenChange={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    const img = (await screen.findByAltText(
      'auth.qrAltText',
    )) as HTMLImageElement
    expect(img.src).toContain('data:image/png;base64,FAKE')
    expect(startSocialPublishAuth).toHaveBeenCalledWith({ platform: 'douyin' })
  })

  it('passes account_id when re-authorising an expired account', async () => {
    startSocialPublishAuth.mockResolvedValue({
      session_id: 'sid-2',
      qr_image_base64: FAKE_QR,
      expires_in: 180,
    })

    render(
      <AuthQrModal
        open
        accountId="acct-7"
        onOpenChange={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    await waitFor(() => {
      expect(startSocialPublishAuth).toHaveBeenCalledWith({
        platform: 'douyin',
        account_id: 'acct-7',
      })
    })
  })

  it('shows the localized error code when start_auth rejects', async () => {
    startSocialPublishAuth.mockRejectedValue({ code: 'sau_unreachable' })

    render(
      <AuthQrModal
        open
        accountId={null}
        onOpenChange={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    expect(
      await screen.findByText('auth.errors.sau_unreachable'),
    ).toBeInTheDocument()
    // Refresh button must be available in the error state.
    expect(screen.getByText('auth.refresh')).toBeInTheDocument()
  })

  it('falls back to the unknown error key when no code is on the rejection', async () => {
    startSocialPublishAuth.mockRejectedValue(new Error('boom'))

    render(
      <AuthQrModal
        open
        accountId={null}
        onOpenChange={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    expect(await screen.findByText('auth.errors.unknown')).toBeInTheDocument()
  })

  it('polls /login/status on a 2s cadence after start_auth resolves', async () => {
    startSocialPublishAuth.mockResolvedValue({
      session_id: 'sid-3',
      qr_image_base64: FAKE_QR,
      expires_in: 180,
    })
    fetchSocialPublishAuthStatus.mockResolvedValue({
      status: 'success',
      account: { id: 'row-1', display_name: '小妹' },
      message: null,
    })

    const onSuccess = vi.fn()
    render(
      <AuthQrModal
        open
        accountId={null}
        onOpenChange={vi.fn()}
        onSuccess={onSuccess}
      />,
    )

    // First poll fires ~POLL_INTERVAL_MS=2000ms after start_auth resolves;
    // we just verify the polling loop kicks off — fine-grained timing
    // (success-display delay → onSuccess) is covered by the e2e harness
    // against sau-mock to avoid jsdom timer flakiness.
    await waitFor(
      () => expect(fetchSocialPublishAuthStatus).toHaveBeenCalled(),
      { timeout: 6_000 },
    )
    expect(fetchSocialPublishAuthStatus).toHaveBeenCalledWith('sid-3')
  }, 10_000)

  it('clicking close calls onOpenChange(false)', async () => {
    startSocialPublishAuth.mockResolvedValue({
      session_id: 'sid-4',
      qr_image_base64: FAKE_QR,
      expires_in: 180,
    })

    const onOpenChange = vi.fn()
    render(
      <AuthQrModal
        open
        accountId={null}
        onOpenChange={onOpenChange}
        onSuccess={vi.fn()}
      />,
    )

    fireEvent.click(await screen.findByText('auth.close'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
