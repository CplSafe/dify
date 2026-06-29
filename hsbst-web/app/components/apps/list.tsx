'use client'

import type { FC } from 'react'
import { RiRefreshLine } from '@remixicon/react'
import { useEffect, useRef } from 'react'
import Button from '@/app/components/base/button'
import { useAppContext } from '@/context/app-context'
import { useInfiniteAppList } from '@/service/use-apps'
import AppCard from './app-card'
import { AppCardSkeleton } from './app-card-skeleton'

type Props = {
  controlRefreshList?: number
}

const List: FC<Props> = ({
  controlRefreshList = 0,
}) => {
  const { isCurrentWorkspaceDatasetOperator } = useAppContext()
  const containerRef = useRef<HTMLDivElement>(null)
  const anchorRef = useRef<HTMLDivElement>(null)
  const appListQueryParams = {
    page: 1,
    limit: 30,
    is_created_by_me: true,
  }

  const {
    data,
    isLoading,
    isFetching,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
    error,
    refetch,
  } = useInfiniteAppList(appListQueryParams, { enabled: !isCurrentWorkspaceDatasetOperator })

  useEffect(() => {
    if (controlRefreshList > 0)
      refetch()
  }, [controlRefreshList, refetch])

  useEffect(() => {
    const hasMore = hasNextPage ?? true
    let observer: IntersectionObserver | undefined

    if (error)
      return

    if (anchorRef.current && containerRef.current) {
      observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !isLoading && !isFetchingNextPage && !error && hasMore)
          fetchNextPage()
      }, {
        root: containerRef.current,
        rootMargin: '160px',
        threshold: 0.1,
      })
      observer.observe(anchorRef.current)
    }
    return () => observer?.disconnect()
  }, [isLoading, isFetchingNextPage, fetchNextPage, error, hasNextPage])

  const pages = data?.pages ?? []
  const apps = pages.flatMap(({ data: apps }) => apps)
  const showSkeleton = isLoading || (isFetching && pages.length === 0)

  return (
    <div ref={containerRef} className="relative flex h-0 shrink-0 grow flex-col overflow-y-auto bg-background-body">
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-y-2 bg-background-body px-12 pb-5 pt-7">
        <div>
          <h2 className="title-2xl-semi-bold text-text-primary">我的应用</h2>
          <p className="mt-1 text-text-tertiary system-sm-regular">选择一个应用进入访问 API、日志与标注、监测。</p>
        </div>
        <Button variant="secondary" onClick={() => refetch()}>
          <RiRefreshLine className="mr-1 h-4 w-4" />
          刷新
        </Button>
      </div>
      <div className="relative grid grow grid-cols-1 content-start gap-4 px-12 pt-2 sm:grid-cols-1 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5 2k:grid-cols-6">
        {showSkeleton && <AppCardSkeleton count={6} />}
        {!showSkeleton && apps.map(app => (
          <AppCard key={app.id} app={app} onRefresh={refetch} />
        ))}
        {!showSkeleton && apps.length === 0 && (
          <div className="col-span-full flex h-40 items-center justify-center rounded-xl border border-dashed border-divider-regular text-text-tertiary system-sm-regular">
            暂无应用
          </div>
        )}
        {isFetchingNextPage && <AppCardSkeleton count={3} />}
      </div>
      <div ref={anchorRef} className="h-0"> </div>
    </div>
  )
}

export default List
