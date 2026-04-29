import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AssetLibraryPage from '../asset-library-page'

const mockReplace = vi.hoisted(() => vi.fn())
const mockRefetch = vi.hoisted(() => vi.fn())
const mockUseAssetLibraryList = vi.hoisted(() => vi.fn())
const mockNavigationState = vi.hoisted(() => ({
  search: '',
}))

vi.mock('@/next/navigation', () => ({
  usePathname: () => '/creator-asset-library',
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => new URLSearchParams(mockNavigationState.search),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/service/use-asset-library', () => ({
  useAssetLibraryList: mockUseAssetLibraryList,
}))

vi.mock('../asset-tabs', () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string
    onChange: (value: string) => void
  }) => (
    <div data-testid="tabs" data-value={value}>
      <button type="button" onClick={() => onChange('audio')}>
        audio-tab
      </button>
      <button type="button" onClick={() => onChange('prompt')}>
        prompt-tab
      </button>
    </div>
  ),
}))

vi.mock('../asset-filter-bar', () => ({
  default: ({
    keyword,
    category,
    tags,
    onKeywordChange,
    onCategoryChange,
    onTagsChange,
  }: {
    keyword: string
    category: string | undefined
    tags: string[]
    onKeywordChange: (value: string) => void
    onCategoryChange: (value: string | undefined) => void
    onTagsChange: (value: string[]) => void
  }) => (
    <div
      data-testid="filters"
      data-category={category ?? ''}
      data-keyword={keyword}
      data-tags={tags.join(',')}
    >
      <button type="button" onClick={() => onKeywordChange('hero')}>
        search-hero
      </button>
      <button type="button" onClick={() => onCategoryChange('marketing')}>
        category-marketing
      </button>
      <button type="button" onClick={() => onTagsChange(['tag-1'])}>
        tag-one
      </button>
    </div>
  ),
}))

vi.mock('../asset-grid', () => ({
  default: ({
    items,
    loading,
    onSelect,
  }: {
    items: unknown[]
    loading: boolean
    onSelect: (id: string) => void
  }) => (
    <div data-testid="grid" data-count={items.length} data-loading={loading}>
      <button type="button" onClick={() => onSelect('asset-1')}>
        select-grid-asset
      </button>
    </div>
  ),
}))

vi.mock('../asset-list', () => ({
  default: ({
    items,
    loading,
    onSelect,
  }: {
    items: unknown[]
    loading: boolean
    onSelect: (id: string) => void
  }) => (
    <div data-testid="list" data-count={items.length} data-loading={loading}>
      <button type="button" onClick={() => onSelect('asset-3')}>
        select-list-asset
      </button>
    </div>
  ),
}))

vi.mock('../upload-dropzone', () => ({
  default: ({
    defaultAssetType,
    onUploaded,
  }: {
    defaultAssetType: string
    onUploaded: () => void
  }) => (
    <button
      type="button"
      data-testid="upload"
      data-type={defaultAssetType}
      onClick={onUploaded}
    >
      upload
    </button>
  ),
}))

vi.mock('../prompt-dialog', () => ({
  default: ({ onCreated }: { onCreated: () => void }) => (
    <button type="button" data-testid="prompt-dialog" onClick={onCreated}>
      prompt-dialog
    </button>
  ),
}))

vi.mock('../asset-detail-drawer', () => ({
  default: ({
    assetId,
    onClose,
    onMutated,
  }: {
    assetId: string | null
    onClose: () => void
    onMutated: () => void
  }) => (
    <div data-testid="detail-drawer" data-asset-id={assetId ?? ''}>
      <button type="button" onClick={onClose}>
        close-detail
      </button>
      <button type="button" onClick={onMutated}>
        mutated-detail
      </button>
    </div>
  ),
}))

vi.mock('../pagination', () => ({
  default: ({
    page,
    total,
    limit,
    hasMore,
    onChange,
  }: {
    page: number
    total: number
    limit: number
    hasMore: boolean
    onChange: (page: number) => void
  }) => (
    <button
      type="button"
      data-testid="pagination"
      data-page={page}
      data-total={total}
      data-limit={limit}
      data-has-more={hasMore}
      onClick={() => onChange(page + 1)}
    >
      next-page
    </button>
  ),
}))

describe('AssetLibraryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockNavigationState.search = ''
    mockUseAssetLibraryList.mockReturnValue({
      data: {
        data: [{ id: 'asset-1' }],
        total: 45,
        page: 1,
        limit: 20,
        has_more: true,
      },
      isLoading: false,
      refetch: mockRefetch,
    })
  })

  it('should render the default grid page and query all assets', () => {
    render(<AssetLibraryPage />)

    expect(screen.getByRole('heading', { name: 'title' })).toBeInTheDocument()
    expect(screen.getByTestId('tabs')).toHaveAttribute('data-value', 'all')
    expect(screen.getByTestId('upload')).toHaveAttribute('data-type', 'image')
    expect(screen.getByTestId('grid')).toHaveAttribute('data-count', '1')
    expect(mockUseAssetLibraryList).toHaveBeenLastCalledWith({
      type: undefined,
      keyword: undefined,
      category: undefined,
      tags: undefined,
      page: 1,
      limit: 20,
    })
  })

  it('should switch tabs and choose the matching list surface', () => {
    render(<AssetLibraryPage />)

    fireEvent.click(screen.getByRole('button', { name: 'audio-tab' }))

    expect(screen.getByTestId('tabs')).toHaveAttribute('data-value', 'audio')
    expect(screen.getByTestId('upload')).toHaveAttribute('data-type', 'audio')
    expect(screen.getByTestId('list')).toBeInTheDocument()
    expect(mockUseAssetLibraryList).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: 'audio', page: 1 }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'prompt-tab' }))

    expect(screen.queryByTestId('upload')).not.toBeInTheDocument()
    expect(screen.getByTestId('prompt-dialog')).toBeInTheDocument()
    expect(screen.getByTestId('list')).toBeInTheDocument()
    expect(mockUseAssetLibraryList).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: 'prompt', page: 1 }),
    )
  })

  it('should reset page when filters change', () => {
    render(<AssetLibraryPage />)

    fireEvent.click(screen.getByRole('button', { name: 'next-page' }))
    expect(mockUseAssetLibraryList).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'search-hero' }))
    expect(mockUseAssetLibraryList).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: 'hero', page: 1 }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'category-marketing' }))
    expect(mockUseAssetLibraryList).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: 'marketing', page: 1 }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'tag-one' }))
    expect(mockUseAssetLibraryList).toHaveBeenLastCalledWith(
      expect.objectContaining({ tags: ['tag-1'], page: 1 }),
    )
  })

  it('should preserve existing query params when opening and closing detail', () => {
    mockNavigationState.search = 'asset_id=asset-2&foo=bar'

    render(<AssetLibraryPage />)

    expect(screen.getByTestId('detail-drawer')).toHaveAttribute(
      'data-asset-id',
      'asset-2',
    )

    fireEvent.click(screen.getByRole('button', { name: 'select-grid-asset' }))
    expect(mockReplace).toHaveBeenCalledWith(
      '/creator-asset-library?asset_id=asset-1&foo=bar',
    )

    fireEvent.click(screen.getByRole('button', { name: 'close-detail' }))
    expect(mockReplace).toHaveBeenCalledWith('/creator-asset-library?foo=bar')
  })

  it('should omit the trailing query marker when the last detail param is cleared', () => {
    mockNavigationState.search = 'asset_id=asset-2'

    render(<AssetLibraryPage />)

    fireEvent.click(screen.getByRole('button', { name: 'close-detail' }))

    expect(mockReplace).toHaveBeenCalledWith('/creator-asset-library')
  })

  it('should refetch after upload, prompt creation, and detail mutation', () => {
    render(<AssetLibraryPage />)

    fireEvent.click(screen.getByTestId('upload'))
    fireEvent.click(screen.getByRole('button', { name: 'mutated-detail' }))
    fireEvent.click(screen.getByRole('button', { name: 'prompt-tab' }))
    fireEvent.click(screen.getByTestId('prompt-dialog'))

    expect(mockRefetch).toHaveBeenCalledTimes(3)
  })
})
