import type { AssetLibraryItem } from '@/contract/console/asset-library'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AssetDetailDrawer from '../asset-detail-drawer'

const mockUseAssetDetail = vi.hoisted(() => vi.fn())
const mockPatchMutate = vi.hoisted(() => vi.fn())
const mockDeleteMutate = vi.hoisted(() => vi.fn())
const mockToastSuccess = vi.hoisted(() => vi.fn())

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key}:${Object.values(values).join('|')}` : key,
  }),
}))

vi.mock('@/service/use-asset-library', () => ({
  useAssetDetail: mockUseAssetDetail,
  usePatchAsset: () => ({
    isPending: false,
    mutate: mockPatchMutate,
  }),
  useDeleteAsset: () => ({
    isPending: false,
    mutate: mockDeleteMutate,
  }),
}))

vi.mock('@/app/components/base/ui/toast', () => ({
  toast: {
    success: mockToastSuccess,
  },
}))

const createAsset = (
  overrides: Partial<AssetLibraryItem> = {},
): AssetLibraryItem => ({
  id: 'asset-1',
  tenant_id: 'tenant-1',
  asset_type: 'image',
  name: 'Hero image',
  description: 'Original description',
  tags: ['hero'],
  category: 'marketing',
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

const renderDrawer = (
  asset: AssetLibraryItem | null,
  props: Partial<React.ComponentProps<typeof AssetDetailDrawer>> = {},
) => {
  mockUseAssetDetail.mockReturnValue({
    data: asset,
    isLoading: false,
  })

  return render(
    <AssetDetailDrawer
      assetId={asset?.id ?? null}
      onClose={() => {}}
      onMutated={() => {}}
      {...props}
    />,
  )
}

describe('AssetDetailDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPatchMutate.mockImplementation((_input, options?: { onSuccess?: () => void }) => {
      options?.onSuccess?.()
    })
    mockDeleteMutate.mockImplementation((_input, options?: { onSuccess?: () => void }) => {
      options?.onSuccess?.()
    })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it('should render nothing when assetId is null', () => {
    renderDrawer(null)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('should fetch and render detail form when assetId is provided', () => {
    renderDrawer(createAsset())

    expect(mockUseAssetDetail).toHaveBeenCalledWith('asset-1')
    expect(screen.getByRole('img', { name: 'Hero image' })).toHaveAttribute(
      'src',
      'https://cdn.example.com/hero.png',
    )
    expect(screen.getByLabelText('prompt.fields.name')).toHaveValue('Hero image')
  })

  it('should enable save after editing a field', () => {
    renderDrawer(createAsset())

    expect(screen.getByRole('button', { name: 'detail.save' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('prompt.fields.name'), {
      target: { value: 'Updated hero' },
    })

    expect(screen.getByRole('button', { name: 'detail.save' })).toBeEnabled()
  })

  it('should patch asset and call onMutated after save', async () => {
    const onMutated = vi.fn()
    renderDrawer(createAsset(), { onMutated })

    fireEvent.change(screen.getByLabelText('prompt.fields.name'), {
      target: { value: 'Updated hero' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'detail.save' }))

    await waitFor(() => {
      expect(mockPatchMutate).toHaveBeenCalledWith(
        {
          asset_id: 'asset-1',
          body: {
            name: 'Updated hero',
            description: 'Original description',
            tags: ['hero'],
            category: 'marketing',
          },
        },
        expect.objectContaining({ onSuccess: expect.any(Function) }),
      )
    })
    expect(onMutated).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'detail.save' })).toBeDisabled()
  })

  it('should open confirm dialog and delete asset', async () => {
    const onClose = vi.fn()
    const onMutated = vi.fn()
    renderDrawer(createAsset(), { onClose, onMutated })

    fireEvent.click(screen.getByRole('button', { name: 'detail.delete' }))
    expect(screen.getByText('detail.deleteConfirmTitle')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'detail.deleteConfirm' }))

    await waitFor(() => {
      expect(mockDeleteMutate).toHaveBeenCalledWith(
        'asset-1',
        expect.objectContaining({ onSuccess: expect.any(Function) }),
      )
    })
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onMutated).toHaveBeenCalledTimes(1)
  })

  it('should render video and audio previews', () => {
    renderDrawer(createAsset({ asset_type: 'video' }))
    expect(screen.getByTestId('asset-preview-video')).toHaveAttribute(
      'src',
      'https://cdn.example.com/hero.png',
    )

    renderDrawer(createAsset({ asset_type: 'audio' }))
    expect(screen.getByTestId('asset-preview-audio')).toHaveAttribute(
      'src',
      'https://cdn.example.com/hero.png',
    )
  })

  it('should copy prompt content', async () => {
    renderDrawer(createAsset({
      asset_type: 'prompt',
      content: 'Write a title',
      signed_url: null,
      upload_file_id: null,
    }))

    expect(screen.getAllByText('Write a title').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'detail.copyContent' }))

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Write a title')
    })
    expect(mockToastSuccess).toHaveBeenCalledWith('detail.copiedToast')
  })
})
