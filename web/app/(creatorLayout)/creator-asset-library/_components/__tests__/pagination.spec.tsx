import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Pagination from '../pagination'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { current?: number, total?: number }) =>
      key === 'pagination.page'
        ? `${key}:${values?.current}/${values?.total}`
        : key,
  }),
}))

const baseProps = {
  page: 2,
  total: 45,
  limit: 20,
  hasMore: true,
  onChange: vi.fn(),
}

describe('Pagination', () => {
  it('should render nothing when total is not greater than limit', () => {
    const { container } = render(
      <Pagination
        {...baseProps}
        total={20}
      />,
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('should render previous, next, and page text', () => {
    render(<Pagination {...baseProps} />)

    expect(screen.getByRole('button', { name: 'pagination.previous' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'pagination.next' })).toBeInTheDocument()
    expect(screen.getByText('pagination.page:2/3')).toBeInTheDocument()
  })

  it('should disable previous on page 1 and next when hasMore is false', () => {
    render(
      <Pagination
        {...baseProps}
        page={1}
        hasMore={false}
      />,
    )

    expect(screen.getByRole('button', { name: 'pagination.previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'pagination.next' })).toBeDisabled()
  })

  it('should call onChange with the previous and next page', () => {
    const onChange = vi.fn()
    render(<Pagination {...baseProps} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'pagination.previous' }))
    fireEvent.click(screen.getByRole('button', { name: 'pagination.next' }))

    expect(onChange).toHaveBeenNthCalledWith(1, 1)
    expect(onChange).toHaveBeenNthCalledWith(2, 3)
  })
})
