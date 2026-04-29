import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AssetGrid from '../asset-grid'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const createAsset = (
  overrides: Partial<AssetLibraryItem> = {},
): AssetLibraryItem => ({
  id: 'asset-1',
  tenant_id: 'tenant-1',
  asset_type: 'image',
  name: 'Hero image',
  description: null,
  tags: [],
  category: null,
  upload_file_id: 'file-1',
  cover_url: null,
  signed_url: 'https://cdn.example.com/hero.png',
  duration: null,
  width: 640,
  height: 480,
  file_size: 1024,
  content: null,
  prompt_variables: [],
  created_by: { id: 'user-1', name: 'Alice', avatar: null },
  created_at: 0,
  updated_at: 0,
  ...overrides,
})

describe('AssetGrid', () => {
  it('should render skeletons while loading', () => {
    render(<AssetGrid items={[]} loading onSelect={() => {}} />)

    expect(screen.getAllByTestId('asset-skeleton')).toHaveLength(6)
  })

  it('should show empty state when not loading and no items exist', () => {
    render(<AssetGrid items={[]} loading={false} onSelect={() => {}} />)

    expect(screen.getByText('empty.all')).toBeInTheDocument()
  })

  it('should call onSelect when a card is clicked', () => {
    const onSelect = vi.fn()
    render(<AssetGrid items={[createAsset()]} loading={false} onSelect={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: 'Hero image' }))

    expect(onSelect).toHaveBeenCalledWith('asset-1')
  })

  it('should render an image asset with signed_url', () => {
    render(<AssetGrid items={[createAsset()]} loading={false} onSelect={() => {}} />)

    expect(screen.getByRole('img', { name: 'Hero image' })).toHaveAttribute(
      'src',
      'https://cdn.example.com/hero.png',
    )
  })

  it('should render a video duration badge', () => {
    render(
      <AssetGrid
        items={[
          createAsset({
            asset_type: 'video',
            cover_url: 'https://cdn.example.com/cover.jpg',
            duration: 15.2,
          }),
        ]}
        loading={false}
        onSelect={() => {}}
      />,
    )

    expect(screen.getByText('15.2s')).toBeInTheDocument()
  })

  it('should render a placeholder when no preview URL exists', () => {
    render(
      <AssetGrid
        items={[createAsset({ signed_url: null })]}
        loading={false}
        onSelect={() => {}}
      />,
    )

    expect(screen.getByTestId('asset-placeholder')).toBeInTheDocument()
  })
})
