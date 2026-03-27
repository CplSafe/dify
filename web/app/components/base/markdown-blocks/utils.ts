import type { ReactNode } from 'react'
import { Children } from 'react'
import { ALLOW_UNSAFE_DATA_SCHEME, MARKETPLACE_API_PREFIX } from '@/config'

type MdastNode = {
  tagName?: string
  children?: MdastNode[]
  [key: string]: unknown
}

export const hasImageChild = (children: MdastNode[] | undefined): boolean => {
  return children?.some((child) => {
    if (child.tagName === 'img')
      return true
    return child.children ? hasImageChild(child.children) : false
  }) ?? false
}

export const isValidUrl = (url: string): boolean => {
  const validPrefixes = ['http:', 'https:', '//', 'mailto:', 'tel:']
  if (ALLOW_UNSAFE_DATA_SCHEME)
    validPrefixes.push('data:')
  return validPrefixes.some(prefix => url.startsWith(prefix))
}

export const getMarkdownImageURL = (url: string, pathname?: string) => {
  const regex = /(^\.\/_assets|^_assets)/
  if (regex.test(url))
    return `${MARKETPLACE_API_PREFIX}${MARKETPLACE_API_PREFIX.endsWith('/') ? '' : '/'}plugins/${pathname ?? ''}${url.replace(regex, '/_assets')}`
  return url
}

const MARKDOWN_IMAGE_LITERAL_PATTERN = /^!\[[^\]]*\]\([^\n)]+\)$/

export const getRenderableImageParagraphChildren = (children: ReactNode): ReactNode[] => {
  return Children.toArray(children).filter((child) => {
    if (typeof child !== 'string')
      return true

    const trimmed = child.trim()
    if (!trimmed)
      return false

    return !MARKDOWN_IMAGE_LITERAL_PATTERN.test(trimmed)
  })
}
