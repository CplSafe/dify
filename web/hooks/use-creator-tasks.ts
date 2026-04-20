'use client'

import type {
  CreatorTask,
  CreatorTaskListResponse,
  UpdateTaskPayload,
} from '@/service/creator-task'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteCreatorTask,
  listCreatorTasks,
  updateCreatorTask,
} from '@/service/creator-task'

const POLL_INTERVAL_MS = 5000
const IN_PROGRESS_STATUSES: readonly string[] = ['running', 'waiting_input']

const EMPTY_RESPONSE: CreatorTaskListResponse = {
  tasks: [],
  total: 0,
  in_progress_count: 0,
}

const isInProgress = (status: string | undefined): boolean =>
  status != null && IN_PROGRESS_STATUSES.includes(status)

const hasConflictStatus = (err: unknown): boolean =>
  typeof err === 'object'
  && err !== null
  && 'status' in err
  && (err as { status: unknown }).status === 409

export function useCreatorTasks() {
  const [data, setData] = useState<CreatorTaskListResponse>(EMPTY_RESPONSE)
  const [loading, setLoading] = useState(false)
  const isFetchingRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchTasks = useCallback(async () => {
    if (isFetchingRef.current)
      return
    isFetchingRef.current = true
    try {
      const result = await listCreatorTasks()
      setData({
        tasks: Array.isArray(result?.tasks) ? result.tasks : [],
        total: result?.total ?? 0,
        in_progress_count: result?.in_progress_count ?? 0,
      })
    }
    catch {
      // stale data is acceptable on network errors
    }
    finally {
      isFetchingRef.current = false
    }
  }, [])

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible')
        fetchTasks()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () =>
      document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [fetchTasks])

  useEffect(() => {
    if (data.in_progress_count <= 0)
      return
    const tick = () => {
      timerRef.current = setTimeout(async () => {
        await fetchTasks()
        tick()
      }, POLL_INTERVAL_MS)
    }
    tick()
    return () => {
      if (timerRef.current)
        clearTimeout(timerRef.current)
    }
  }, [data.in_progress_count, fetchTasks])

  const refresh = useCallback(async () => {
    setLoading(true)
    await fetchTasks()
    setLoading(false)
  }, [fetchTasks])

  const replaceTask = useCallback((taskId: string, updated: CreatorTask) => {
    setData((prev) => {
      const prevStatus = prev.tasks.find(t => t.id === taskId)?.status
      const delta
        = Number(isInProgress(updated.status)) - Number(isInProgress(prevStatus))
      return {
        ...prev,
        tasks: prev.tasks.map(t => (t.id === taskId ? updated : t)),
        in_progress_count: prev.in_progress_count + delta,
      }
    })
  }, [])

  const updateTask = useCallback(
    async (
      taskId: string,
      payload: UpdateTaskPayload,
    ): Promise<CreatorTask | null> => {
      try {
        const updated = await updateCreatorTask(taskId, payload)
        replaceTask(taskId, updated)
        return updated
      }
      catch (err: unknown) {
        if (hasConflictStatus(err))
          await fetchTasks()
        return null
      }
    },
    [fetchTasks, replaceTask],
  )

  const renameTask = useCallback(
    async (taskId: string, title: string): Promise<boolean> => {
      try {
        const updated = await updateCreatorTask(taskId, { title })
        setData(prev => ({
          ...prev,
          tasks: prev.tasks.map(t => (t.id === taskId ? updated : t)),
        }))
        return true
      }
      catch {
        return false
      }
    },
    [],
  )

  const deleteTask = useCallback(async (taskId: string): Promise<boolean> => {
    try {
      await deleteCreatorTask(taskId)
      setData((prev) => {
        const task = prev.tasks.find(t => t.id === taskId)
        if (task?.conversation_id) {
          window.dispatchEvent(
            new CustomEvent('creator-task-deleted', {
              detail: { taskId, conversationId: task.conversation_id },
            }),
          )
        }
        return {
          ...prev,
          tasks: prev.tasks.filter(t => t.id !== taskId),
          total: prev.total - 1,
          in_progress_count:
            prev.in_progress_count - Number(isInProgress(task?.status)),
        }
      })
      return true
    }
    catch {
      return false
    }
  }, [])

  return { data, loading, refresh, updateTask, renameTask, deleteTask }
}
