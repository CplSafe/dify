import type { FC } from 'react'
import type { Components } from 'streamdown'
import type { ChatItem } from '../../types'
import { memo } from 'react'
import { Markdown } from '@/app/components/base/markdown'
import { cn } from '@/utils/classnames'

type BasicContentProps = {
  item: ChatItem
  responding?: boolean
  customMarkdownComponents?: Partial<Components>
}
const BasicContent: FC<BasicContentProps> = ({
  item,
  responding,
  customMarkdownComponents,
}) => {
  const { annotation, content } = item

  if (annotation?.logAnnotation) {
    return (
      <Markdown
        className="chat-answer-markdown"
        content={annotation?.logAnnotation.content || ''}
        mode="static"
        customComponents={customMarkdownComponents}
        data-testid="basic-content-markdown"
      />
    )
  }

  // Preserve Windows UNC paths and similar backslash-heavy strings by
  // wrapping them in inline code so Markdown renders backslashes verbatim.
  let displayContent = content
  if (
    typeof content === 'string'
    && /^\\\\\S.*/.test(content)
    && !/^`.*`$/.test(content)
  ) {
    displayContent = `\`${content}\``
  }

  return (
    <Markdown
      className={cn('chat-answer-markdown', item.isError && '!text-[#F04438]')}
      content={displayContent}
      mode={responding ? 'streaming' : 'static'}
      customComponents={customMarkdownComponents}
      data-testid="basic-content-markdown"
    />
  )
}

export default memo(BasicContent)
