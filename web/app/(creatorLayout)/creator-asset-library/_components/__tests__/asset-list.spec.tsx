import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AssetList from '../asset-list'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const createAsset = (
  overrides: Partial<AssetLibraryItem> = {},
): AssetLibraryItem => ({
  id: 'asset-1',
  tenant_id: 'tenant-1',
  asset_type: 'audio',
  name: 'Voice over',
  description: null,
  tags: ['ad', 'voice'],
  category: null,
  upload_file_id: 'file-1',
  cover_url: null,
  signed_url: 'https://cdn.example.com/voice.mp3',
  duration: 65,
  width: null,
  height: null,
  file_size: 1024,
  content: null,
  prompt_variables: [],
  created_by: { id: 'user-1', name: 'Alice', avatar: null },
  created_at: 0,
  updated_at: 0,
  ...overrides,
})

describe('AssetList', () => {
  it('should render skeleton rows while loading', () => {
    render(<AssetList items={[]} loading onSelect={() => {}} />)

    expect(screen.getAllByTestId('asset-skeleton-row')).toHaveLength(5)
  })

  it('should show empty state when not loading and no items exist', () => {
    render(<AssetList items={[]} loading={false} onSelect={() => {}} />)

    expect(screen.getByText('empty.all')).toBeInTheDocument()
  })

  it('should call onSelect when a row is clicked', () => {
    const onSelect = vi.fn()
    render(<AssetList items={[createAsset()]} loading={false} onSelect={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /Voice over/ }))

    expect(onSelect).toHaveBeenCalledWith('asset-1')
  })

  it('should render audio duration, tags, and creator name', () => {
    render(<AssetList items={[createAsset()]} loading={false} onSelect={() => {}} />)

    expect(screen.getByText('1:05')).toBeInTheDocument()
    expect(screen.getByText('ad')).toBeInTheDocument()
    expect(screen.getByText('voice')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
  })

  it('should render truncated prompt content preview', () => {
    const content = 'x'.repeat(60)
    render(
      <AssetList
        items={[
          createAsset({
            asset_type: 'prompt',
            name: 'Prompt',
            content,
            duration: null,
          }),
        ]}
        loading={false}
        onSelect={() => {}}
      />,
    )

    expect(screen.getByText(`${'x'.repeat(50)}...`)).toBeInTheDocument()
  })
})
