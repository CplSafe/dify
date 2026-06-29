'use client'

import type { App } from '@/types/app'
import * as React from 'react'
import { AppTypeIcon } from '@/app/components/app/type-selector'
import AppIcon from '@/app/components/base/app-icon'
import { useAppContext } from '@/context/app-context'
import { useRouter } from '@/next/navigation'
import { getRedirection } from '@/utils/app-redirection'
import { formatTime } from '@/utils/time'

type AppCardProps = {
  app: App
  onRefresh?: () => void
}

const AppCard = ({ app }: AppCardProps) => {
  const { isCurrentWorkspaceEditor } = useAppContext()
  const { push } = useRouter()
  const editedAt = formatTime({
    date: (app.updated_at || app.created_at) * 1000,
    dateFormat: 'YYYY-MM-DD HH:mm',
  })

  return (
    <div
      onClick={(e) => {
        e.preventDefault()
        getRedirection(isCurrentWorkspaceEditor, app, push)
      }}
      className="group relative col-span-1 inline-flex h-[160px] cursor-pointer flex-col rounded-xl border border-solid border-components-card-border bg-components-card-bg shadow-sm transition-all duration-200 ease-in-out hover:shadow-lg"
    >
      <div className="flex h-[66px] shrink-0 grow-0 items-center gap-3 px-[14px] pb-3 pt-[14px]">
        <div className="relative shrink-0">
          <AppIcon
            size="large"
            iconType={app.icon_type}
            icon={app.icon}
            background={app.icon_background}
            imageUrl={app.icon_url}
          />
          <AppTypeIcon type={app.mode} wrapperClassName="absolute -bottom-0.5 -right-0.5 w-4 h-4 shadow-sm" className="h-3 w-3" />
        </div>
        <div className="w-0 grow py-px">
          <div className="flex items-center text-sm font-semibold leading-5 text-text-secondary">
            <div className="truncate" title={app.name}>{app.name}</div>
          </div>
          <div className="flex items-center gap-1 text-[10px] font-medium leading-[18px] text-text-tertiary">
            <div className="truncate" title={app.author_name}>{app.author_name}</div>
            <div>·</div>
            <div className="truncate" title={editedAt}>{editedAt}</div>
          </div>
        </div>
      </div>
      <div className="title-wrapper h-[90px] px-[14px] text-xs leading-normal text-text-tertiary">
        <div className="line-clamp-2" title={app.description}>
          {app.description}
        </div>
      </div>
    </div>
  )
}

export default React.memo(AppCard)
