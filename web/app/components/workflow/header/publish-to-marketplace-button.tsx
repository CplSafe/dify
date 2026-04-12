import {
  RiStoreLine,
} from '@remixicon/react'
import {
  memo,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useStore as useAppStore } from '@/app/components/app/store'
import { useAppContext } from '@/context/app-context'
import { get, post } from '@/service/base'
import { cn } from '@/utils/classnames'
import TipPopup from '../operator/tip-popup'

const PublishToMarketplaceButton = () => {
  const { isSystemAdmin } = useAppContext()
  const { appDetail } = useAppStore(useShallow(state => ({
    appDetail: state.appDetail,
  })))
  const [publishedAt, setPublishedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const appId = appDetail?.id

  useEffect(() => {
    if (!appId || !isSystemAdmin)
      return
    get<{ published_at?: string }>(`/creator/marketplace/apps/${appId}/status`)
      .then((data) => {
        if (data?.published_at)
          setPublishedAt(data.published_at)
      })
      .catch(() => {})
  }, [appId, isSystemAdmin])

  const handlePublish = useCallback(async () => {
    if (!appId || loading)
      return
    setLoading(true)
    try {
      const data = await post<{ published_at?: string }>('/creator/marketplace/apps', { body: { app_id: appId } })
      setPublishedAt(data.published_at ?? new Date().toISOString())
    }
    catch {}
    finally {
      setLoading(false)
    }
  }, [appId, loading])

  if (!isSystemAdmin)
    return null

  const dateLabel = publishedAt
    ? new Date(publishedAt).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
    : null

  return (
    <TipPopup title={publishedAt ? `已发布 ${dateLabel}` : '发布到应用市场'}>
      <div
        className={cn(
          'flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-[13px] font-medium',
          publishedAt
            ? 'text-util-colors-green-green-600 hover:bg-state-success-hover'
            : 'text-components-button-secondary-accent-text hover:bg-state-accent-hover',
          loading && 'cursor-not-allowed opacity-50',
        )}
        onClick={handlePublish}
      >
        <RiStoreLine className="h-4 w-4" />
        {dateLabel
          ? (
              <span>
                {dateLabel}
                {' '}
                已发布
              </span>
            )
          : <span>发布</span>}
      </div>
    </TipPopup>
  )
}

export default memo(PublishToMarketplaceButton)
