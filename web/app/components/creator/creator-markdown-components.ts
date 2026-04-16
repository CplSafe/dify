/**
 * Markdown customComponents map for creator mode.
 *
 * Separated from the component definitions to satisfy
 * react-refresh/only-export-components (files exporting both components
 * and non-component values break fast refresh).
 */
import type { Components } from 'streamdown'
import { createElement } from 'react'
import { CreatorImg, CreatorVideoBlock } from './markdown-save-overrides'

export const creatorMarkdownComponents: Partial<Components> = {
  img: props => createElement(CreatorImg, { src: String(props.src ?? '') }),
  video: CreatorVideoBlock as Components['video'],
}
