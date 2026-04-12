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
      className={cn('rounded-[32px] border border-[#E9E9EB] bg-white p-5 shadow-[0_8px_30px_rgb(0,0,0,0.04)]', className)}
      data-testid="content-wrapper"
    >
      <div className="flex items-center gap-2 px-1 pt-1 pb-4 border-b border-[#F4F4F5] mb-4">
        {/* node icon */}
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
          <BlockIcon type={BlockEnum.HumanInput} className="shrink-0 scale-90" />
        </div>
        {/* node name */}
        <div
          className="text-[15px] font-bold grow truncate text-text-primary"
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
        <div className="px-1">
          {/* human input form content */}
          {children}
        </div>
      )}
    </div>
  )
}

export default ContentWrapper
