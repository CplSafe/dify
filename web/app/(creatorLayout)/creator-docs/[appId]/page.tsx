'use client'

import type { App } from '@/types/app'
import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useStore as useAppStore } from '@/app/components/app/store'
import CopyFeedback from '@/app/components/base/copy-feedback'
import Loading from '@/app/components/base/loading'
import { CreatorKeyButton } from '@/app/components/creator/creator-key-modal'
import Doc from '@/app/components/develop/doc'
import { get } from '@/service/base'

export default function CreatorDocsPage() {
  const { appId } = useParams<{ appId: string }>()
  const appDetail = useAppStore(state => state.appDetail)
  const setAppDetail = useAppStore(state => state.setAppDetail)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!appId)
      return
    setLoading(true)
    setAppDetail()
    get<App>(`/creator/marketplace/apps/${appId}/detail`)
      .then((res: App) => setAppDetail(res))
      .catch((e: any) => {
        if (e?.status === 404 || e?.status === 403)
          setNotFound(true)
      })
      .finally(() => setLoading(false))
  }, [appId, setAppDetail])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loading />
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-text-tertiary">
        <div className="mb-2 text-lg font-semibold">应用不存在</div>
        <div className="text-sm">该应用可能已被下架或您没有访问权限</div>
      </div>
    )
  }

  if (!appDetail)
    return null

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      {/* Header: same layout as DevelopMain, but API Key button shows global creator key */}
      <div className="flex shrink-0 items-center justify-between border-b border-solid border-b-divider-regular px-6 py-2">
        <div className="text-lg font-medium text-text-primary" />
        <div className="flex flex-wrap items-center gap-y-2">
          {/* API Base URL */}
          <div className="mr-2 flex h-8 items-center rounded-lg border-[0.5px] border-components-input-border-active bg-components-input-bg-normal pl-1.5 pr-1 leading-5">
            <div className="mr-0.5 h-5 shrink-0 rounded-md border border-divider-subtle px-1.5 text-[11px] text-text-tertiary">
              API SERVER
            </div>
            <div className="w-fit truncate px-1 text-[13px] font-medium text-text-secondary sm:w-[248px]">
              {appDetail.api_base_url}
            </div>
            <div className="mx-1 h-[14px] w-px bg-divider-regular" />
            <CopyFeedback content={appDetail.api_base_url} />
          </div>
          {/* Global creator API key — replaces per-app SecretKeyButton */}
          <CreatorKeyButton className="h-8! shrink-0" />
        </div>
      </div>

      {/* Docs content */}
      <div className="grow overflow-auto px-4 py-4 sm:px-10">
        <Doc appDetail={appDetail} />
      </div>
    </div>
  )
}
