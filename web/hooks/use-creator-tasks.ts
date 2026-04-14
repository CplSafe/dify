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
const IN_PROGRESS_STATUSES = ['running', 'waiting_input'] as const

function isInProgress(status: string): boolean {
  return (IN_PROGRESS_STATUSES as readonly string[]).includes(status)
}

function hasConflictStatus(err: unknown): boolean {
  return (
    typeof err === 'object'
    && err !== null
    && 'status' in err
    && (err as { status: unknown }).status === 409
  )
}

export function useCreatorTasks() {
  const [data, setData] = useState<CreatorTaskListResponse>({
    tasks: [],
    total: 0,
    in_progress_count: 0,
  })
  const [loading, setLoading] = useState(false)
  const isFetchingRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inProgressRef = useRef(false)

  const fetchTasks = useCallback(async () => {
    if (isFetchingRef.current)
      return
    isFetchingRef.current = true
    try {
      const result = await listCreatorTasks()
      inProgressRef.current = result.in_progress_count > 0
      setData(result)
    }
    catch {
      // stale data is acceptable on network errors
    }
    finally {
      isFetchingRef.current = false
    }
  }, [])

  const scheduleNextPoll = useCallback(() => {
    if (timerRef.current)
      clearTimeout(timerRef.current)
    if (inProgressRef.current) {
      timerRef.current = setTimeout(async () => {
        await fetchTasks()
        scheduleNextPoll()
      }, POLL_INTERVAL_MS)
    }
  }, [fetchTasks])

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
    inProgressRef.current = data.in_progress_count > 0
    scheduleNextPoll()
    return () => {
      if (timerRef.current)
        clearTimeout(timerRef.current)
    }
  }, [data.in_progress_count, scheduleNextPoll])

  const refresh = useCallback(async () => {
    setLoading(true)
    await fetchTasks()
    setLoading(false)
  }, [fetchTasks])

  const updateTask = useCallback(
    async (
      taskId: string,
      payload: UpdateTaskPayload,
    ): Promise<CreatorTask | null> => {
      try {
        const updated = await updateCreatorTask(taskId, payload)
        setData((prev) => {
          const wasInProgress = isInProgress(
            prev.tasks.find(t => t.id === taskId)?.status ?? '',
          )
          const nowInProgress = isInProgress(updated.status)
          const delta = Number(nowInProgress) - Number(wasInProgress)
          return {
            ...prev,
            tasks: prev.tasks.map(t => (t.id === taskId ? updated : t)),
            in_progress_count: prev.in_progress_count + delta,
          }
        })
        return updated
      }
      catch (err: unknown) {
        if (hasConflictStatus(err))
          await fetchTasks()
        return null
      }
    },
    [fetchTasks],
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
        const wasInProgress = isInProgress(task?.status ?? '')
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
          in_progress_count: wasInProgress
            ? prev.in_progress_count - 1
            : prev.in_progress_count,
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
