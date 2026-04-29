import { describe, expect, it, vi } from 'vitest'

import { uploadAssetFile } from './asset-library'
import { upload } from './base'

vi.mock('./base', () => ({
  upload: vi.fn(),
}))

describe('uploadAssetFile', () => {
  it('builds FormData with file, asset_type, and JSON-encoded tags', async () => {
    const mockUpload = vi.mocked(upload)
    mockUpload.mockResolvedValue({ id: 'asset-1' } as never)

    const file = new File([new Uint8Array([1, 2, 3])], 'picture.png', {
      type: 'image/png',
    })

    await uploadAssetFile({
      file,
      asset_type: 'image',
      name: 'picture',
      tags: ['cover', 'product'],
      category: 'marketing',
      description: 'hero image',
    })

    expect(mockUpload).toHaveBeenCalledTimes(1)
    const [opts, isPublic, url] = mockUpload.mock.calls[0]
    expect(isPublic).toBe(false)
    expect(url).toBe('/asset-library/files')
    expect(opts.data).toBeInstanceOf(FormData)

    const fd = opts.data as FormData
    expect(fd.get('asset_type')).toBe('image')
    expect(fd.get('name')).toBe('picture')
    expect(fd.get('tags')).toBe('["cover","product"]')
    expect(fd.get('category')).toBe('marketing')
    expect(fd.get('description')).toBe('hero image')
    expect(fd.get('file')).toBeInstanceOf(File)
  })

  it('omits optional fields when not provided and sends an empty tags array', async () => {
    const mockUpload = vi.mocked(upload)
    mockUpload.mockResolvedValue({ id: 'asset-2' } as never)

    const file = new File(['x'], 'audio.mp3', { type: 'audio/mpeg' })
    await uploadAssetFile({ file, asset_type: 'audio' })

    const fd = mockUpload.mock.calls.at(-1)![0].data as FormData
    expect(fd.get('name')).toBeNull()
    expect(fd.get('description')).toBeNull()
    expect(fd.get('category')).toBeNull()
    expect(fd.get('tags')).toBe('[]')
  })

  it('wires onProgress to xhr.upload.onprogress', async () => {
    const mockUpload = vi.mocked(upload)
    mockUpload.mockImplementation(async (opts) => {
      opts.xhr.upload.dispatchEvent(new ProgressEvent('progress', {
        lengthComputable: true,
        loaded: 50,
        total: 100,
      }))
      return { id: 'asset-3' } as never
    })

    const events: number[] = []
    await uploadAssetFile({
      file: new File(['x'], 'picture.png', { type: 'image/png' }),
      asset_type: 'image',
      onProgress: percent => events.push(percent),
    })

    expect(events).toEqual([50])
  })
})
