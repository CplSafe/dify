'use client'

import type { TabValue } from './asset-tabs'
import type { AssetType } from '@/contract/console/asset-library'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePathname, useRouter, useSearchParams } from '@/next/navigation'
import { useAssetLibraryList } from '@/service/use-asset-library'
import AssetDetailDrawer from './asset-detail-drawer'
import AssetFilterBar from './asset-filter-bar'
import AssetGrid from './asset-grid'
import AssetList from './asset-list'
import AssetTabs from './asset-tabs'
import Pagination from './pagination'
import PromptDialog from './prompt-dialog'
import UploadDropzone from './upload-dropzone'

const PAGE_SIZE = 20

type UploadableAssetType = Exclude<AssetType, 'prompt'>

export default function AssetLibraryPage() {
  const { t } = useTranslation('assetLibrary')
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const [tab, setTab] = useState<TabValue>('all')
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState<string | undefined>()
  const [tags, setTags] = useState<string[]>([])
  const [page, setPage] = useState(1)

  const detailAssetId = searchParams.get('asset_id')
  const list = useAssetLibraryList({
    type: tab === 'all' ? undefined : tab,
    keyword: keyword || undefined,
    category,
    tags: tags.length > 0 ? tags : undefined,
    page,
    limit: PAGE_SIZE,
  })

  const setDetailAssetId = (id: string | null) => {
    const next = new URLSearchParams(searchParams.toString())

    if (id)
      next.set('asset_id', id)
    else
      next.delete('asset_id')

    const queryString = next.toString()
    router.replace(queryString ? `${pathname}?${queryString}` : pathname)
  }

  const resetPage = () => {
    setPage(1)
  }

  const handleTabChange = (value: TabValue) => {
    setTab(value)
    resetPage()
  }

  const handleKeywordChange = (value: string) => {
    setKeyword(value)
    resetPage()
  }

  const handleCategoryChange = (value: string | undefined) => {
    setCategory(value)
    resetPage()
  }

  const handleTagsChange = (value: string[]) => {
    setTags(value)
    resetPage()
  }

  const isGridMode = tab === 'all' || tab === 'image' || tab === 'video'
  const uploadAssetType: UploadableAssetType
    = tab === 'audio' || tab === 'image' || tab === 'video' ? tab : 'image'
  const uploadEntry = tab !== 'prompt'
    ? (
        <UploadDropzone
          defaultAssetType={uploadAssetType}
          variant={isGridMode ? 'tile' : 'list-item'}
          onUploaded={() => list.refetch()}
        />
      )
    : null

  return (
    <div className="flex h-full min-h-0 flex-col px-8 py-6">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">
          {t('title')}
        </h1>
        {tab === 'prompt' && (
          <PromptDialog onCreated={() => list.refetch()} />
        )}
      </header>

      <AssetTabs value={tab} onChange={handleTabChange} />
      <AssetFilterBar
        keyword={keyword}
        category={category}
        tags={tags}
        onKeywordChange={handleKeywordChange}
        onCategoryChange={handleCategoryChange}
        onTagsChange={handleTagsChange}
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isGridMode
          ? (
              <AssetGrid
                items={list.data?.data ?? []}
                leading={uploadEntry}
                loading={list.isLoading}
                onSelect={setDetailAssetId}
              />
            )
          : (
              <AssetList
                items={list.data?.data ?? []}
                leading={uploadEntry}
                loading={list.isLoading}
                onSelect={setDetailAssetId}
              />
            )}
      </div>

      <Pagination
        page={page}
        total={list.data?.total ?? 0}
        limit={PAGE_SIZE}
        hasMore={list.data?.has_more ?? false}
        onChange={setPage}
      />

      <AssetDetailDrawer
        assetId={detailAssetId}
        onClose={() => setDetailAssetId(null)}
        onMutated={() => list.refetch()}
      />
    </div>
  )
}
