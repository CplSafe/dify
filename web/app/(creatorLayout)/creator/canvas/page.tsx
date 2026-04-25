'use client'

import type { UserCanvas } from '@/service/user-canvases'
import { RiAddCircleLine, RiDeleteBinLine } from '@remixicon/react'
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from '@/next/navigation'
import { deleteUserCanvas, listUserCanvases } from '@/service/user-canvases'

const CanvasListPage = () => {
  const router = useRouter()
  const [items, setItems] = useState<UserCanvas[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const reload = useCallback(async () => {
    setError(null)
    try {
      const resp = await listUserCanvases()
      setItems(resp.data)
    }
    catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载画布列表失败')
      setItems([])
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const handleOpen = useCallback(
    (canvas: UserCanvas) => {
      router.push(`/creator/canvas/${canvas.app_id}?canvas_id=${canvas.id}`)
    },
    [router],
  )

  const handleDelete = useCallback(
    async (canvas: UserCanvas) => {
      // eslint-disable-next-line no-alert -- TODO: replace with AlertDialog once CR7 ships
      if (!window.confirm(`删除画布「${canvas.title}」？此操作不可恢复。`))
        return
      setDeletingId(canvas.id)
      try {
        await deleteUserCanvas(canvas.id)
        await reload()
      }
      catch (e: unknown) {
        setError(e instanceof Error ? e.message : '删除失败，请重试')
      }
      finally {
        setDeletingId(null)
      }
    },
    [reload],
  )

  if (items === null) {
    return (
      <div className="flex h-full items-center justify-center text-text-tertiary">
        加载中…
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4">
        <div>
          <div className="title-2xl-semi-bold text-text-primary">我的画布</div>
          <div className="mt-1 system-xs-regular text-text-tertiary">
            保存过的运行快照，按时间倒序。
          </div>
        </div>
      </div>
      {error && (
        <div className="mx-6 mb-3 rounded-md border border-state-destructive-border bg-state-destructive-hover px-3 py-2 system-xs-regular text-text-destructive">
          {error}
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {items.length === 0
          ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-text-tertiary">
                <RiAddCircleLine className="h-8 w-8" />
                <div className="system-md-medium text-text-primary">
                  暂无保存的画布
                </div>
                <div className="system-sm-regular">
                  打开任意应用的运行画布，完成一次运行后点击右上角「保存为画布」。
                </div>
              </div>
            )
          : (
              <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {items.map(item => (
                  <li
                    key={item.id}
                    className="group rounded-xl border border-components-panel-border bg-components-panel-bg p-4 shadow-xs transition-shadow hover:shadow-md"
                  >
                    <button
                      type="button"
                      onClick={() => handleOpen(item)}
                      className="block w-full text-left"
                    >
                      <div className="truncate system-md-semibold text-text-primary">
                        {item.title}
                      </div>
                      <div className="mt-1 system-xs-regular text-text-tertiary">
                        {item.created_at
                          ? new Date(item.created_at).toLocaleString()
                          : '未知时间'}
                      </div>
                      <div className="mt-2 truncate system-2xs-regular text-text-quaternary">
                        app:
                        {' '}
                        {item.app_id}
                      </div>
                    </button>
                    <div className="mt-3 flex items-center justify-end">
                      <button
                        type="button"
                        onClick={() => handleDelete(item)}
                        disabled={deletingId === item.id}
                        aria-label="删除"
                        className="flex h-7 items-center gap-1 rounded-md px-2 system-xs-regular text-text-tertiary opacity-0 transition-opacity group-hover:opacity-100 hover:bg-state-destructive-hover hover:text-text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <RiDeleteBinLine className="h-3.5 w-3.5" />
                        {deletingId === item.id ? '删除中…' : '删除'}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
      </div>
    </div>
  )
}

export default CanvasListPage
