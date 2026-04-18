import type { ComponentProps } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'

import { DeleteAccountConfirm } from '../delete-account-confirm'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const k = (name: string) => `accountList.deleteConfirm.${name}`
const button = (name: string) => screen.getByRole('button', { name: k(name) })

const ACCOUNT = {
  id: 'row-1',
  platform: 'douyin',
  display_name: '小妹',
  avatar_url: null,
  status: 'active',
  last_check_at: null,
  created_at: '2026-04-18T00:00:00',
} as const

type ConfirmProps = ComponentProps<typeof DeleteAccountConfirm>

function renderConfirm(overrides: Partial<ConfirmProps> = {}) {
  const props: ConfirmProps = {
    open: true,
    account: ACCOUNT,
    loading: false,
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
    ...overrides,
  }
  render(<DeleteAccountConfirm {...props} />)
  return props
}

describe('DeleteAccountConfirm', () => {
  it('renders nothing when closed', () => {
    renderConfirm({ open: false })
    expect(screen.queryByText(k('title'))).not.toBeInTheDocument()
  })

  it('shows the account display_name when open', async () => {
    renderConfirm()
    expect(await screen.findByText(k('title'))).toBeInTheDocument()
    expect(screen.getByText(ACCOUNT.display_name)).toBeInTheDocument()
  })

  it('fires onConfirm and onCancel from the matching buttons', async () => {
    const { onCancel, onConfirm } = renderConfirm()
    await screen.findByText(k('title'))

    fireEvent.click(button('confirm'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()

    fireEvent.click(button('cancel'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('disables both buttons while loading=true', async () => {
    renderConfirm({ loading: true })
    await screen.findByText(k('title'))

    // BaseUI may strip disabled buttons from the accessibility tree, so the
    // role-based query fails. Walk up from the visible label text instead
    // and check either signal (native `disabled` or `aria-disabled`).
    for (const name of ['confirm', 'cancel'] as const) {
      const btn = screen.getByText(k(name)).closest('button')
      expect(btn).not.toBeNull()
      const ariaDisabled = btn?.getAttribute('aria-disabled')
      const nativeDisabled = btn?.disabled
      expect(ariaDisabled === 'true' || nativeDisabled).toBe(true)
    }
  })
})
