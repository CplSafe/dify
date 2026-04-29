import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AssetFilterBar from '../asset-filter-bar'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: { tag?: string }) =>
      values?.tag ? `${key}:${values.tag}` : key,
  }),
}))

const baseProps = {
  keyword: '',
  category: undefined,
  tags: [] as string[],
  onKeywordChange: vi.fn(),
  onCategoryChange: vi.fn(),
  onTagsChange: vi.fn(),
}

describe('AssetFilterBar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should render search, category, and tags inputs', () => {
    render(<AssetFilterBar {...baseProps} />)

    expect(screen.getByPlaceholderText('filters.searchPlaceholder')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('filters.categoryPlaceholder')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('filters.tagsPlaceholder')).toBeInTheDocument()
  })

  it('should debounce search input by 300ms', () => {
    vi.useFakeTimers()
    const onKeywordChange = vi.fn()
    render(
      <AssetFilterBar
        {...baseProps}
        onKeywordChange={onKeywordChange}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText('filters.searchPlaceholder'), {
      target: { value: 'hero' },
    })

    expect(onKeywordChange).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(onKeywordChange).toHaveBeenCalledWith('hero')
  })

  it('should add a tag when Enter is pressed', async () => {
    const onTagsChange = vi.fn()
    render(<AssetFilterBar {...baseProps} onTagsChange={onTagsChange} />)

    await userEvent.type(
      screen.getByPlaceholderText('filters.tagsPlaceholder'),
      'newtag{Enter}',
    )

    expect(onTagsChange).toHaveBeenCalledWith(['newtag'])
  })

  it('should remove a tag when its chip button is clicked', () => {
    const onTagsChange = vi.fn()
    render(
      <AssetFilterBar
        {...baseProps}
        tags={['a', 'b']}
        onTagsChange={onTagsChange}
      />,
    )

    fireEvent.click(screen.getByLabelText('filters.removeTag:a'))

    expect(onTagsChange).toHaveBeenCalledWith(['b'])
  })

  it('should ignore duplicate tag add', async () => {
    const onTagsChange = vi.fn()
    render(
      <AssetFilterBar
        {...baseProps}
        tags={['a']}
        onTagsChange={onTagsChange}
      />,
    )

    await userEvent.type(screen.getByPlaceholderText('filters.tagsPlaceholder'), 'a{Enter}')

    expect(onTagsChange).not.toHaveBeenCalled()
  })

  it('should not add an empty tag', async () => {
    const onTagsChange = vi.fn()
    render(<AssetFilterBar {...baseProps} onTagsChange={onTagsChange} />)

    await userEvent.type(
      screen.getByPlaceholderText('filters.tagsPlaceholder'),
      '   {Enter}',
    )

    expect(onTagsChange).not.toHaveBeenCalled()
  })
})
