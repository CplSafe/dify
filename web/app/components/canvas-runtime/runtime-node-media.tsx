'use client'

import type { FC } from 'react'
import { useMemo } from 'react'
import { cn } from '@/utils/classnames'

type MediaKind = 'image' | 'video' | 'audio'

type MediaItem = {
  kind: MediaKind
  url: string
}

const IMAGE_EXT = /\.(?:png|jpe?g|gif|webp|bmp|svg)(?:\?|#|$)/i
const VIDEO_EXT = /\.(?:mp4|webm|mov|m4v|ogv)(?:\?|#|$)/i
const AUDIO_EXT = /\.(?:mp3|wav|m4a|ogg|flac|aac)(?:\?|#|$)/i

const _looksLikeUrl = (s: string) =>
  /^https?:\/\//i.test(s) || s.startsWith('/files/') || s.startsWith('data:')

const _kindFromString = (s: string): MediaKind | null => {
  if (!_looksLikeUrl(s))
    return null
  if (IMAGE_EXT.test(s) || s.startsWith('data:image/'))
    return 'image'
  if (VIDEO_EXT.test(s) || s.startsWith('data:video/'))
    return 'video'
  if (AUDIO_EXT.test(s) || s.startsWith('data:audio/'))
    return 'audio'
  return null
}

const _kindFromObject = (
  obj: Record<string, unknown>,
): { kind: MediaKind, url: string } | null => {
  const url
    = (typeof obj.url === 'string' && obj.url)
      || (typeof obj.preview_url === 'string' && obj.preview_url)
      || ''
  if (!url)
    return null
  // Dify's file convention carries `type: 'image' | 'video' | 'audio' | ...`.
  const declared = (obj.type as string | undefined)?.toLowerCase()
  if (declared === 'image' || declared === 'video' || declared === 'audio')
    return { kind: declared, url }
  // Fallback to extension sniffing on the URL.
  const sniffed = _kindFromString(url)
  if (sniffed)
    return { kind: sniffed, url }
  return null
}

/**
 * Walk a node's outputs looking for media references. Handles three
 * common shapes:
 *   1. A bare URL string in any value.
 *   2. An array of strings or `{url, type}` objects.
 *   3. A nested object with a `url` key (Dify's file convention).
 *
 * Stops at the first 8 items so a noisy node can't blow out the card.
 */
const _collectMedia = (outputs?: Record<string, unknown>): MediaItem[] => {
  if (!outputs)
    return []
  const out: MediaItem[] = []
  const visit = (v: unknown) => {
    if (out.length >= 8)
      return
    if (typeof v === 'string') {
      const k = _kindFromString(v)
      if (k)
        out.push({ kind: k, url: v })
      return
    }
    if (Array.isArray(v)) {
      for (const item of v) visit(item)
      return
    }
    if (v && typeof v === 'object') {
      const obj = v as Record<string, unknown>
      const direct = _kindFromObject(obj)
      if (direct) {
        out.push(direct)
        return
      }
      // Recurse into known container keys only — avoids touching prompt
      // text or other non-asset payloads.
      for (const key of ['files', 'images', 'urls', 'data', 'items']) {
        if (key in obj)
          visit(obj[key])
      }
    }
  }
  visit(outputs)
  return out
}

type NodeMediaPreviewProps = {
  outputs?: Record<string, unknown>
}

/**
 * Inline asset preview painted into the runtime node card. Renders a
 * compact gallery so authors / end users can see (and play) the actual
 * media a node produced — stills, video, audio — without needing to
 * open a side panel.
 *
 * Layout decisions:
 *   - Fixed 88px-tall preview row keeps cards visually uniform.
 *   - Single item fills the row; >1 items stack horizontally with
 *     overflow scroll (touch-friendly).
 *   - Video / audio use native HTML elements with `controls` so we
 *     inherit browser playback affordances for free.
 */
const NodeMediaPreview: FC<NodeMediaPreviewProps> = ({ outputs }) => {
  const items = useMemo(() => _collectMedia(outputs), [outputs])
  if (items.length === 0)
    return null

  const single = items.length === 1
  return (
    <div
      className={cn(
        'mt-1 flex h-22 gap-1.5 overflow-x-auto rounded-md bg-background-section',
        single ? 'justify-center' : 'snap-x snap-mandatory',
      )}
      data-testid="runtime-node-media"
    >
      {items.map((item, idx) => (
        <div
          key={`${item.url}-${idx}`}
          className={cn(
            'shrink-0 snap-start',
            single ? 'h-22 w-full' : 'h-22 w-22',
          )}
        >
          {item.kind === 'image' && (
            <img
              src={item.url}
              alt=""
              loading="lazy"
              className="h-full w-full rounded-md object-cover"
            />
          )}
          {item.kind === 'video' && (
            <video
              src={item.url}
              controls
              preload="metadata"
              className="h-full w-full rounded-md bg-black object-contain"
            />
          )}
          {item.kind === 'audio' && (
            <audio
              src={item.url}
              controls
              preload="metadata"
              className="h-full w-full"
            />
          )}
        </div>
      ))}
    </div>
  )
}

export default NodeMediaPreview
