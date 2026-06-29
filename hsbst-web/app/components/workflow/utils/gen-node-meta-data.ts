import type { BlockEnum } from '@/app/components/workflow/types'
import type { UseDifyNodesPath } from '@/types/doc-paths'
import { BlockClassificationEnum } from '@/app/components/workflow/block-selector/types'
import { DEFAULT_BRAND_NAME, HELP_CENTER_ENABLED } from '@/config'

type GenNodeMetaDataParams = {
  classification?: BlockClassificationEnum
  sort: number
  type: BlockEnum
  title?: string
  author?: string
  helpLinkUri?: UseDifyNodesPath
  isRequired?: boolean
  isUndeletable?: boolean
  isStart?: boolean
  isSingleton?: boolean
  isTypeFixed?: boolean
}
export const genNodeMetaData = ({
  classification = BlockClassificationEnum.Default,
  sort,
  type,
  title = '',
  author = DEFAULT_BRAND_NAME,
  helpLinkUri,
  isRequired = false,
  isUndeletable = false,
  isStart = false,
  isSingleton = false,
  isTypeFixed = false,
}: GenNodeMetaDataParams) => {
  return {
    classification,
    sort,
    type,
    title,
    author,
    helpLinkUri: HELP_CENTER_ENABLED ? (helpLinkUri || type) : undefined,
    isRequired,
    isUndeletable,
    isStart,
    isSingleton,
    isTypeFixed,
  }
}
