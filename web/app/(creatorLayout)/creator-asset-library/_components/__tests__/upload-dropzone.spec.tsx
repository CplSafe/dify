import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UploadDropzone from '../upload-dropzone'

const mockMutateAsync = vi.hoisted(() => vi.fn())
const mockToastError = vi.hoisted(() => vi.fn())

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key}:${Object.values(values).join('|')}` : key,
  }),
}))

vi.mock('@/service/use-asset-library', () => ({
  useUploadAssetFile: () => ({
    mutateAsync: mockMutateAsync,
  }),
}))

vi.mock('@/app/components/base/ui/toast', () => ({
  toast: {
    error: mockToastError,
  },
}))

const dropFile = (file: File) => {
  fireEvent.drop(screen.getByTestId('asset-dropzone'), {
    dataTransfer: { files: [file] },
  })
}

describe('UploadDropzone', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render idle and active drag text', () => {
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)

    expect(screen.getByText('upload.dropzoneIdle')).toBeInTheDocument()

    fireEvent.dragOver(screen.getByTestId('asset-dropzone'))

    expect(screen.getByText('upload.dropzoneActive')).toBeInTheDocument()
  })

  it('should reject non-whitelisted MIME types', async () => {
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)

    dropFile(new File(['x'], 'bitmap.bmp', { type: 'image/bmp' }))

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('upload.unsupportedMime:image/bmp')
    })
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('should reject files larger than 200MB', async () => {
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)
    const file = new File(['x'], 'large.png', { type: 'image/png' })
    Object.defineProperty(file, 'size', { value: 201 * 1024 * 1024 })

    dropFile(file)

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('upload.fileTooLarge')
    })
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('should start upload for allowed MIME types', async () => {
    mockMutateAsync.mockResolvedValueOnce({})
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)
    const file = new File(['x'], 'hero.png', { type: 'image/png' })

    dropFile(file)

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalled()
    })
    expect(mockMutateAsync.mock.calls[0][0]).toMatchObject({
      file,
      asset_type: 'image',
      name: 'hero.png',
    })
  })

  it('should infer asset_type from MIME type', async () => {
    mockMutateAsync.mockResolvedValueOnce({})
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)

    dropFile(new File(['x'], 'voice.mp3', { type: 'audio/mpeg' }))

    await waitFor(() => {
      expect(mockMutateAsync.mock.calls[0][0]).toMatchObject({
        asset_type: 'audio',
      })
    })
  })

  it('should show progress for multiple files and clear chips on success', async () => {
    const resolvers: Array<() => void> = []
    mockMutateAsync.mockImplementation((body) => {
      body.onProgress(35)
      return new Promise<void>((resolve) => {
        resolvers.push(resolve)
      })
    })
    const onUploaded = vi.fn()
    render(<UploadDropzone defaultAssetType="image" onUploaded={onUploaded} />)

    fireEvent.drop(screen.getByTestId('asset-dropzone'), {
      dataTransfer: {
        files: [
          new File(['x'], 'one.png', { type: 'image/png' }),
          new File(['x'], 'two.png', { type: 'image/png' }),
        ],
      },
    })

    expect(await screen.findByText('upload.uploading:one.png')).toBeInTheDocument()
    expect(screen.getByText('upload.uploading:two.png')).toBeInTheDocument()
    expect(screen.getAllByText('35%')).toHaveLength(2)

    resolvers.forEach(resolve => resolve())

    await waitFor(() => {
      expect(screen.queryByText('upload.uploading:one.png')).not.toBeInTheDocument()
    })
    expect(onUploaded).toHaveBeenCalledTimes(2)
  })

  it('should keep failed upload chip and dismiss it', async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error('network down'))
    render(<UploadDropzone defaultAssetType="image" onUploaded={() => {}} />)

    dropFile(new File(['x'], 'broken.png', { type: 'image/png' }))

    expect(await screen.findByText('upload.uploadFailed:network down')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('upload.dismissProgress'))

    expect(screen.queryByText('upload.uploadFailed:network down')).not.toBeInTheDocument()
  })
})
