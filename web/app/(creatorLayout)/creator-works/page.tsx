'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { del, get, post } from '@/service/base'

type Work = {
  id: string
  title: string
  file_key: string | null
  file_type: string
  share_status: string
  created_at: string
  updated_at: string
  output_data: string | null
  workflow_run_id: string | null
}

const shareStatusLabel: Record<string, string> = {
  draft: '草稿',
  published_tiktok: '已发布至抖音',
  published_xhs: '已发布至小红书',
}

const shareStatusColor: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-600',
  published_tiktok: 'bg-pink-100 text-pink-700',
  published_xhs: 'bg-red-100 text-red-700',
}

export default function CreatorWorksPage() {
  const [works, setWorks] = useState<Work[]>([])
  const [loading, setLoading] = useState(true)
  const [publishing, setPublishing] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const loadWorksRef = useRef(() => {})
  loadWorksRef.current = () => {
    get<{ data: Work[] }>('/creator/works')
      .then(data => setWorks(data.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadWorksRef.current()

    const handleVisibility = () => {
      if (document.visibilityState === 'visible')
        loadWorksRef.current()
    }
    const handleFocus = () => loadWorksRef.current()
    document.addEventListener('visibilitychange', handleVisibility)
    window.addEventListener('focus', handleFocus)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility)
      window.removeEventListener('focus', handleFocus)
    }
  }, [])

  const reload = useCallback(() => {
    loadWorksRef.current()
  }, [])

  const handlePublish = async (workId: string, platform: 'tiktok' | 'xhs') => {
    setPublishing(workId)
    try {
      await post(`/creator/works/${workId}/publish`, { body: { platform } })
      reload()
    }
    catch {
    }
    finally {
      setPublishing(null)
    }
  }

  const handleDelete = async (workId: string) => {
    setDeletingId(workId)
  }

  const confirmDelete = async (workId: string) => {
    try {
      await del(`/creator/works/${workId}`)
      setWorks(prev => prev.filter(w => w.id !== workId))
    }
    catch {
    }
    finally {
      setDeletingId(null)
    }
  }

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })

  const renderPreview = (work: Work) => {
    if (work.file_key && work.file_type === 'image') {
      return (
        <div className="flex h-40 items-center justify-center overflow-hidden bg-gray-50">
          <img
            src={work.file_key}
            alt={work.title}
            className="h-full w-full object-cover"
            onError={e => (e.currentTarget.style.display = 'none')}
          />
        </div>
      )
    }

    if (work.file_key && work.file_type === 'video') {
      return (
        <div className="flex h-40 items-center justify-center overflow-hidden bg-black">
          <video
            src={work.file_key}
            className="h-full w-full object-contain"
            muted
            preload="metadata"
          />
        </div>
      )
    }

    const iconClass
      = work.file_type === 'image' ? 'i-ri-image-line' : 'i-ri-video-line'
    return (
      <div className="flex h-40 items-center justify-center bg-gradient-to-br from-primary-50 to-purple-50">
        <span className={`${iconClass} h-16 w-16 text-primary-200`} />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-divider-subtle px-8 py-6">
        <h1 className="text-2xl font-bold text-text-primary">发布作品</h1>
        <p className="mt-1 text-text-quaternary">
          管理您的创作内容，一键发布至抖音、小红书
        </p>
      </div>

      <div className="flex-1 p-8">
        {loading
          ? (
              <div className="flex h-48 items-center justify-center text-text-quaternary">
                加载中...
              </div>
            )
          : works.length === 0
            ? (
                <div className="flex h-48 flex-col items-center justify-center text-text-quaternary">
                  <span className="mb-3 i-ri-video-line h-12 w-12 opacity-30" />
                  <p>还没有创作内容</p>
                  <p className="mt-1 text-sm">
                    在首页使用 AI 工作流生成内容后，作品将显示在这里
                  </p>
                </div>
              )
            : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {works.map(work => (
                    <div
                      key={work.id}
                      className="flex flex-col overflow-hidden rounded-2xl border border-divider-subtle bg-background-default"
                    >
                      {renderPreview(work)}

                      <div className="flex flex-1 flex-col p-4">
                        <div className="mb-2 flex items-start justify-between">
                          <h3 className="line-clamp-1 flex-1 font-medium text-text-primary">
                            {work.title}
                          </h3>
                          <span
                            className={`ml-2 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${shareStatusColor[work.share_status] || 'bg-gray-100 text-gray-600'}`}
                          >
                            {shareStatusLabel[work.share_status] || work.share_status}
                          </span>
                        </div>

                        <div className="mb-4 flex items-center gap-1 text-xs text-text-quaternary">
                          <span className="i-ri-time-line h-3 w-3" />
                          <span>{formatDate(work.created_at)}</span>
                        </div>

                        {work.share_status === 'draft'
                          ? (
                              <div className="mt-auto flex gap-2">
                                <button
                                  onClick={() => handlePublish(work.id, 'tiktok')}
                                  disabled={publishing === work.id}
                                  className="flex-1 rounded-lg bg-black py-2 text-xs font-medium text-white transition-colors hover:bg-gray-800 disabled:opacity-50"
                                >
                                  {publishing === work.id ? '发布中...' : '发布至抖音'}
                                </button>
                                <button
                                  onClick={() => handlePublish(work.id, 'xhs')}
                                  disabled={publishing === work.id}
                                  className="flex-1 rounded-lg bg-red-500 py-2 text-xs font-medium text-white transition-colors hover:bg-red-600 disabled:opacity-50"
                                >
                                  发布至小红书
                                </button>
                              </div>
                            )
                          : (
                              <div className="mt-auto flex items-center gap-2 text-sm text-green-600">
                                <span className="i-ri-check-line h-4 w-4" />
                                <span>已发布</span>
                              </div>
                            )}

                        {deletingId === work.id
                          ? (
                              <div className="mt-2 flex items-center justify-center gap-2 rounded-lg bg-red-50 py-1.5 text-xs">
                                <span className="text-red-600">确认删除？</span>
                                <button
                                  onClick={() => confirmDelete(work.id)}
                                  className="rounded bg-red-500 px-2 py-0.5 text-white hover:bg-red-600"
                                >
                                  确认
                                </button>
                                <button
                                  onClick={() => setDeletingId(null)}
                                  className="rounded bg-gray-200 px-2 py-0.5 text-gray-600 hover:bg-gray-300"
                                >
                                  取消
                                </button>
                              </div>
                            )
                          : (
                              <button
                                onClick={() => handleDelete(work.id)}
                                className="mt-2 flex items-center justify-center gap-1 rounded-lg py-1.5 text-xs text-text-quaternary transition-colors hover:bg-state-destructive-hover hover:text-red-600"
                              >
                                <span className="i-ri-delete-bin-6-line h-3 w-3" />
                                <span>删除</span>
                              </button>
                            )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
      </div>
    </div>
  )
}
