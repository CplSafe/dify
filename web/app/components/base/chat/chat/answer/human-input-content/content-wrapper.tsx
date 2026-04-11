import { useCallback, useState } from 'react'
import BlockIcon from '@/app/components/workflow/block-icon'
import { BlockEnum } from '@/app/components/workflow/types'
import { cn } from '@/utils/classnames'

type ContentWrapperProps = {
  nodeTitle: string
  children: React.ReactNode
  showExpandIcon?: boolean
  className?: string
  expanded?: boolean
}

const ContentWrapper = ({
  nodeTitle,
  children,
  showExpandIcon = false,
  className,
  expanded = false,
}: ContentWrapperProps) => {
  const [isExpanded, setIsExpanded] = useState(expanded)

  const handleToggleExpand = useCallback(() => {
    setIsExpanded(!isExpanded)
  }, [isExpanded])

  return (
    <div
      className={cn('rounded-[24px] border border-components-panel-border-subtle bg-background-default/95 p-3 shadow-sm backdrop-blur-xs', className)}
      data-testid="content-wrapper"
    >
      <div className="flex items-center gap-2 px-2 pt-1 pb-2">
        {/* node icon */}
        <BlockIcon type={BlockEnum.HumanInput} className="shrink-0" />
        {/* node name */}
        <div
          className="system-sm-semibold-uppercase grow truncate text-text-primary"
          title={nodeTitle}
        >
          {nodeTitle}
        </div>
        {showExpandIcon && (
          <div
            className="shrink-0 cursor-pointer"
            onClick={handleToggleExpand}
            data-testid="expand-icon"
          >
            {
              isExpanded
                ? (
                    <div className="i-ri-arrow-down-s-line size-4" />
                  )
                : (
                    <div className="i-ri-arrow-right-s-line size-4" />
                  )
            }
          </div>
        )}
      </div>
      {(!showExpandIcon || isExpanded) && (
        <div className="rounded-2xl bg-background-section px-3 py-3">
          {/* human input form content */}
          {children}
        </div>
      )}
    </div>
  )
}

export default ContentWrapper
