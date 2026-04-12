/**
 * @fileoverview Utility functions for preprocessing Markdown content.
 * These functions were extracted from the main markdown renderer for better separation of concerns.
 * Includes preprocessing for LaTeX and custom "think" tags.
 */
import { flow } from 'es-toolkit/compat'
import { ALLOW_UNSAFE_DATA_SCHEME } from '@/config'

const PHONE_PATTERN_SOURCE = String.raw`\+?\d[\d \t\-()]{5,}\d`
const PHONE_PATTERN = new RegExp(PHONE_PATTERN_SOURCE, 'g')
const PHONE_FIELD_LABELS = ['咨询电话', '监督投诉电话'] as const
const LABELED_PHONE_PATTERN = new RegExp(
  String.raw`((?:${PHONE_FIELD_LABELS.join('|')})[：:]\s*)(${PHONE_PATTERN_SOURCE})`,
  'g',
)
const CODE_OR_LINK_PLACEHOLDER_PREFIX = '__MARKDOWN_PHONE_PLACEHOLDER__'
const IMAGE_GALLERY_TAG = 'image-gallery'
const IMAGE_LINE_PATTERN = /^!\[[^\]]*\]\(([^)\n]+)\)$/

const normalizeTelHref = (value: string) => {
  const trimmed = value.trim()
  const normalized = trimmed.replace(/[^\d+]/g, '')
  const digitsOnly = normalized.replace(/\D/g, '')

  if (digitsOnly.length < 7)
    return null

  return normalized.startsWith('+') ? normalized : digitsOnly
}

export const preprocessPhoneLinks = (content: string) => {
  if (typeof content !== 'string' || !content)
    return content

  const preservedSegments: string[] = []
  const preserveSegment = (segment: string) => {
    const placeholder = `${CODE_OR_LINK_PLACEHOLDER_PREFIX}${preservedSegments.length}__`
    preservedSegments.push(segment)
    return placeholder
  }

  let processedContent = content
    .replace(/```[\s\S]*?```/g, preserveSegment)
    .replace(/`[^`\n]+`/g, preserveSegment)
    .replace(/!?\[[^\]]*\]\([^)\n]+\)/g, preserveSegment)
    .replace(/<[^>\n]+>/g, preserveSegment)

  processedContent = processedContent.replace(LABELED_PHONE_PATTERN, (_match, prefix: string, phone: string) => {
    const telHref = normalizeTelHref(phone)
    if (!telHref)
      return `${prefix}${phone}`

    return `${prefix}[${phone}](tel:${telHref})`
  })

  preservedSegments.forEach((segment, index) => {
    processedContent = processedContent.replace(`${CODE_OR_LINK_PLACEHOLDER_PREFIX}${index}__`, segment)
  })

  return processedContent
}

export const preprocessImageGallery = (content: string) => {
  if (typeof content !== 'string' || !content)
    return content

  const lines = content.split('\n')
  const result: string[] = []

  let index = 0
  while (index < lines.length) {
    let cursor = index
    const imageUrls: string[] = []

    while (cursor < lines.length) {
      const trimmed = lines[cursor].trim()
      if (!trimmed) {
        if (imageUrls.length > 0) {
          cursor += 1
          continue
        }
        break
      }

      const match = trimmed.match(IMAGE_LINE_PATTERN)
      if (!match)
        break

      imageUrls.push(match[1])
      cursor += 1
    }

    if (imageUrls.length >= 2) {
      result.push(
        `<${IMAGE_GALLERY_TAG} data-srcs="${imageUrls.map(url => encodeURIComponent(url)).join(',')}"></${IMAGE_GALLERY_TAG}>`,
      )
      index = cursor
      continue
    }

    if (cursor > index) {
      result.push(...lines.slice(index, cursor))
      index = cursor
      continue
    }

    result.push(lines[index])
    index += 1
  }

  return result.join('\n')
}

export const preprocessLaTeX = (content: string) => {
  if (typeof content !== 'string')
    return content

  const codeBlockRegex = /```[\s\S]*?```/g
  const codeBlocks = content.match(codeBlockRegex) || []
  const escapeReplacement = (str: string) => str.replace(/\$/g, '_TMP_REPLACE_DOLLAR_')
  let processedContent = content.replace(codeBlockRegex, 'CODE_BLOCK_PLACEHOLDER')

  processedContent = flow([
    (str: string) => str.replace(/\\\[(.*?)\\\]/g, (_, equation) => `$$${equation}$$`),
    (str: string) => str.replace(/\\\[([\s\S]*?)\\\]/g, (_, equation) => `$$${equation}$$`),
    (str: string) => str.replace(/\\\((.*?)\\\)/g, (_, equation) => `$$${equation}$$`),
    (str: string) => str.replace(/(^|[^\\])\$(.+?)\$/g, (_, prefix, equation) => `${prefix}$${equation}$`),
  ])(processedContent)

  codeBlocks.forEach((block) => {
    processedContent = processedContent.replace('CODE_BLOCK_PLACEHOLDER', escapeReplacement(block))
  })

  processedContent = processedContent.replace(/_TMP_REPLACE_DOLLAR_/g, '$')

  return processedContent
}

export const preprocessThinkTag = (content: string) => {
  const thinkOpenTagRegex = /(<think>\s*)+/g
  const thinkCloseTagRegex = /(\s*<\/think>)+/g
  return flow([
    (str: string) => str.replace(thinkOpenTagRegex, '<details data-think=true>\n'),
    (str: string) => str.replace(thinkCloseTagRegex, '\n[ENDTHINKFLAG]</details>'),
    (str: string) => str.replace(/(<\/details>)(?![^\S\r\n]*[\r\n])(?![^\S\r\n]*$)/g, '$1\n'),
  ])(content)
}

/**
 * Transforms a URI for use in react-markdown, ensuring security and compatibility.
 * This function is designed to work with react-markdown v9+ which has stricter
 * default URL handling.
 *
 * Behavior:
 * 1. Always allows the custom 'abbr:' protocol.
 * 2. Always allows page-local fragments (e.g., "#some-id").
 * 3. Always allows protocol-relative URLs (e.g., "//example.com/path").
 * 4. Always allows purely relative paths (e.g., "path/to/file", "/abs/path").
 * 5. Allows absolute URLs if their scheme is in a permitted list (case-insensitive):
 *    'http:', 'https:', 'mailto:', 'xmpp:', 'irc:', 'ircs:'.
 * 6. Intelligently distinguishes colons used for schemes from colons within
 *    paths, query parameters, or fragments of relative-like URLs.
 * 7. Returns the original URI if allowed, otherwise returns `undefined` to
 *    signal that the URI should be removed/disallowed by react-markdown.
 */
export const customUrlTransform = (uri: string): string | undefined => {
  const PERMITTED_SCHEME_REGEX = /^(https?|ircs?|mailto|xmpp|abbr|tel):$/i

  if (uri.startsWith('#'))
    return uri

  if (uri.startsWith('//'))
    return uri

  const colonIndex = uri.indexOf(':')

  if (colonIndex === -1)
    return uri

  const slashIndex = uri.indexOf('/')
  const questionMarkIndex = uri.indexOf('?')
  const hashIndex = uri.indexOf('#')

  if (
    (slashIndex !== -1 && colonIndex > slashIndex)
    || (questionMarkIndex !== -1 && colonIndex > questionMarkIndex)
    || (hashIndex !== -1 && colonIndex > hashIndex)
  ) {
    return uri
  }

  const scheme = uri.substring(0, colonIndex + 1).toLowerCase()
  if (PERMITTED_SCHEME_REGEX.test(scheme))
    return uri

  if (ALLOW_UNSAFE_DATA_SCHEME && scheme === 'data:')
    return uri

  return undefined
}
