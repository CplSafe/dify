import type { ExtraProps } from 'streamdown'
import ImageGallery from '@/app/components/base/image-gallery'

type MarkdownImageGalleryProps = {
  node?: ExtraProps['node']
  ['data-srcs']?: string
}

const MarkdownImageGallery = ({ node, ...props }: MarkdownImageGalleryProps) => {
  const rawSrcs = props['data-srcs']
    || ((node?.properties as Record<string, unknown> | undefined)?.dataSrcs as string | undefined)
    || ''

  const srcs = rawSrcs
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
    .map(item => decodeURIComponent(item))

  if (!srcs.length)
    return null

  return (
    <div className="markdown-img-wrapper">
      <ImageGallery srcs={srcs} variant="markdown" />
    </div>
  )
}

export default MarkdownImageGallery
