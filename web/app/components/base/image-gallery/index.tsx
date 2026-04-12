'use client'
import type { FC } from 'react'
import * as React from 'react'
import { useState } from 'react'
import { Carousel } from '@/app/components/base/carousel'
import ImagePreview from '@/app/components/base/image-uploader/image-preview'
import ImagePreviewer from '@/app/components/datasets/common/image-previewer'
import { cn } from '@/utils/classnames'
import s from './style.module.css'

type Props = {
  srcs: string[]
  variant?: 'default' | 'markdown'
}

const getGridWidthStyle = (imgNum: number) => {
  if (imgNum === 1) {
    return {
      maxWidth: '100%',
    }
  }

  if (imgNum === 2 || imgNum === 4) {
    return {
      width: 'calc(50% - 4px)',
    }
  }

  return {
    width: 'calc(33.3333% - 5.3333px)',
  }
}

const ImageGallery: FC<Props> = ({
  srcs,
  variant = 'default',
}) => {
  const [previewIndex, setPreviewIndex] = useState<number | null>(null)

  const validSrcs = srcs.filter(Boolean)
  const imgNum = validSrcs.length
  const isSingleImage = imgNum === 1

  if (!imgNum)
    return null

  if (variant === 'markdown' && imgNum > 1) {
    return (
      <>
        <Carousel
          className={s.markdownCarousel}
          opts={{
            align: 'center',
            containScroll: 'trimSnaps',
            dragFree: false,
            skipSnaps: false,
            loop: false,
          }}
          data-testid="image-gallery"
        >
          <Carousel.Content className={s.markdownCarouselContent}>
            {validSrcs.map((src, index) => (
              <Carousel.Item
                key={`${src}-${index}`}
                className={s.markdownCarouselItem}
              >
                <button
                  type="button"
                  className={cn(s.itemButton, s.markdownButton)}
                  onClick={() => setPreviewIndex(index)}
                  data-testid="gallery-image-button"
                >
                  <div className={s.markdownCardHeader}>
                    <span className={s.markdownCardTitle}>
                      流程图
                      {index + 1}
                    </span>
                    <span className={s.markdownCardMeta}>点击查看</span>
                  </div>
                  <img
                    className={cn(s.item, s.markdownItem)}
                    src={src}
                    alt=""
                    data-testid="gallery-image"
                    onError={e => e.currentTarget.parentElement?.parentElement?.remove()}
                  />
                  <div className={s.markdownCardFooter}>
                    <span className={s.markdownCardCaption}>左右滑动查看</span>
                    <span className={s.markdownCardIndex}>
                      {index + 1}
                      /
                      {imgNum}
                    </span>
                  </div>
                </button>
              </Carousel.Item>
            ))}
          </Carousel.Content>
        </Carousel>
        {previewIndex !== null && (
          <ImagePreviewer
            images={validSrcs.map((url, index) => ({
              url,
              name: `流程图 ${index + 1}`,
              size: 0,
            }))}
            initialIndex={previewIndex}
            onClose={() => setPreviewIndex(null)}
          />
        )}
      </>
    )
  }

  return (
    <div
      className={cn(
        s.gallery,
        s[`img-${imgNum}`],
        isSingleImage ? s.single : s.grid,
      )}
      data-testid="image-gallery"
    >
      {validSrcs.map((src, index) => {
        const gridWidthStyle = getGridWidthStyle(imgNum)

        return (
          <button
            key={`${src}-${index}`}
            type="button"
            className={cn(
              s.itemButton,
              isSingleImage && s.singleButton,
            )}
            style={gridWidthStyle}
            onClick={() => setPreviewIndex(index)}
            data-testid="gallery-image-button"
          >
            <img
              className={cn(s.item, isSingleImage && s.singleItem)}
              style={isSingleImage ? gridWidthStyle : undefined}
              src={src}
              alt=""
              data-testid="gallery-image"
              onError={e => e.currentTarget.parentElement?.remove()}
            />
            {isSingleImage && (
              <span className={s.singleHint}>点击查看大图</span>
            )}
          </button>
        )
      })}
      {
        previewIndex !== null && imgNum > 1 && (
          <ImagePreviewer
            images={validSrcs.map((url, index) => ({
              url,
              name: `图片 ${index + 1}`,
              size: 0,
            }))}
            initialIndex={previewIndex}
            onClose={() => setPreviewIndex(null)}
          />
        )
      }
      {
        previewIndex !== null && imgNum === 1 && (
          <ImagePreview
            url={validSrcs[previewIndex]}
            onCancel={() => setPreviewIndex(null)}
            title=""
          />
        )
      }
    </div>
  )
}

export default React.memo(ImageGallery)

export const ImageGalleryTest = () => {
  const imgGallerySrcs = (() => {
    const srcs = []
    for (let i = 0; i < 6; i++)
      srcs.push('https://placekitten.com/360/360')

    return srcs
  })()
  return (
    <div className="space-y-2">
      {imgGallerySrcs.map((_, index) => (
        <div key={index} className="rounded-lg bg-[#D1E9FF80] p-4 pb-2">
          <ImageGallery srcs={imgGallerySrcs.slice(0, index + 1)} />
        </div>
      ))}
    </div>
  )
}
