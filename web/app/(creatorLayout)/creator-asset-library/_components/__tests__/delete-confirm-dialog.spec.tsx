import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import DeleteConfirmDialog from '../delete-confirm-dialog'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key}:${Object.values(values).join('|')}` : key,
  }),
}))

describe('DeleteConfirmDialog', () => {
  it('should render nothing when closed', () => {
    render(
      <DeleteConfirmDialog
        open={false}
        name="Hero image"
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    )

    expect(screen.queryByText('detail.deleteConfirmTitle')).not.toBeInTheDocument()
  })

  it('should call onConfirm when confirm is clicked', () => {
    const onConfirm = vi.fn()
    render(
      <DeleteConfirmDialog
        open
        name="Hero image"
        onCancel={() => {}}
        onConfirm={onConfirm}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'detail.deleteConfirm' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('should call onCancel when cancel is clicked', async () => {
    const onCancel = vi.fn()
    render(
      <DeleteConfirmDialog
        open
        name="Hero image"
        onCancel={onCancel}
        onConfirm={() => {}}
      />,
    )

    expect(screen.getByText('detail.deleteConfirmBody:Hero image')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'detail.deleteCancel' }))

    await waitFor(() => {
      expect(onCancel).toHaveBeenCalledTimes(1)
    })
  })
})
