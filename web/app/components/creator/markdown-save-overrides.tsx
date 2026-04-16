/* eslint-disable ts/no-explicit-any -- streamdown node types are untyped */
'use client'

/**
 * Markdown component overrides for creator mode.
 *
 * Wraps the standard Img and VideoBlock renderers with a "save to publish
 * center" button so users can selectively save images/videos produced by
 * workflow direct-reply nodes.
 */
import { memo, useMemo } from 'react'
import ImageGallery from '@/app/components/base/image-gallery'
import VideoGallery from '@/app/components/base/video-gallery'
import SaveToWorksButton from './save-to-works-button'

// ---------------------------------------------------------------------------
// Image override
// ---------------------------------------------------------------------------

export const CreatorImg = memo(({ src = '' }: { src?: string }) => {
  const srcs = useMemo(() => [src], [src])
  return (
    <div className="markdown-img-wrapper">
      <ImageGallery srcs={srcs} variant="markdown" />
      <SaveToWorksButton fileUrl={src} fileType="image" />
    </div>
  )
})
CreatorImg.displayName = 'CreatorImg'

// ---------------------------------------------------------------------------
// Video override
// ---------------------------------------------------------------------------

export const CreatorVideoBlock = memo(({ node }: any) => {
  const srcs: string[] = node.children
    .filter((child: any) => 'properties' in child)
    .map((child: any) => child.properties.src)

  const finalSrcs
    = srcs.length > 0
      ? srcs
      : ([node.properties?.src].filter(Boolean) as string[])

  if (finalSrcs.length === 0)
    return null

  return (
    <div>
      <VideoGallery srcs={finalSrcs} />
      {finalSrcs.map(src => (
        <SaveToWorksButton key={src} fileUrl={src} fileType="video" />
      ))}
    </div>
  )
})
CreatorVideoBlock.displayName = 'CreatorVideoBlock'
