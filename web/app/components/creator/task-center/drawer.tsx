'use client'

import type { CreatorTask } from '@/service/creator-task'
import { RiCloseLine, RiRefreshLine } from '@remixicon/react'
import { useEffect, useState } from 'react'
import { useCreatorTasks } from '@/hooks/use-creator-tasks'
import { useRouter } from '@/next/navigation'
import TaskItem from './task-item'

type Tab = 'in_progress' | 'completed'

type Props = {
  onClose: () => void
}

export default function TaskCenterDrawer({ onClose }: Props) {
  const router = useRouter()
  const { data, loading, refresh, renameTask, deleteTask } = useCreatorTasks()
  const [activeTab, setActiveTab] = useState<Tab>('in_progress')

  // Initial load
  useEffect(() => {
    refresh()
  }, [refresh])

  const tasks = data?.tasks ?? []
  const inProgressTasks = tasks.filter(t =>
    ['pending', 'running', 'waiting_input'].includes(t.status),
  )
  const completedTasks = tasks.filter(t =>
    ['completed', 'failed'].includes(t.status),
  )

  const handleTaskClick = (task: CreatorTask) => {
    if (task.conversation_id) {
      router.push(
        `/creator/installed/${task.installed_app_id}?conversationId=${task.conversation_id}`,
      )
    }
    else {
      router.push(`/creator?app_id=${task.app_id}`)
    }
    onClose()
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-divider-subtle px-4 py-3">
        <h2 className="text-base font-semibold text-text-primary">任务中心</h2>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="rounded-lg p-1.5 text-text-tertiary hover:bg-state-base-hover hover:text-text-secondary disabled:opacity-50"
            title="刷新"
          >
            <RiRefreshLine
              className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`}
            />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-tertiary hover:bg-state-base-hover hover:text-text-secondary"
          >
            <RiCloseLine className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 border-b border-divider-subtle">
        <button
          type="button"
          onClick={() => setActiveTab('in_progress')}
          className={[
            'flex-1 px-4 py-2.5 text-sm font-medium transition-colors',
            activeTab === 'in_progress'
              ? 'border-b-2 border-components-button-primary-bg text-components-button-primary-bg'
              : 'text-text-tertiary hover:text-text-secondary',
          ].join(' ')}
        >
          进行中
          {inProgressTasks.length > 0 && (
            <span className="ml-1.5 rounded-full bg-components-button-primary-bg px-1.5 py-0.5 text-xs text-white">
              {inProgressTasks.length}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('completed')}
          className={[
            'flex-1 px-4 py-2.5 text-sm font-medium transition-colors',
            activeTab === 'completed'
              ? 'border-b-2 border-components-button-primary-bg text-components-button-primary-bg'
              : 'text-text-tertiary hover:text-text-secondary',
          ].join(' ')}
        >
          已完成
          {completedTasks.length > 0 && (
            <span className="ml-1.5 rounded-full bg-state-base-hover px-1.5 py-0.5 text-xs text-text-secondary">
              {completedTasks.length}
            </span>
          )}
        </button>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === 'in_progress' && (
          <>
            {inProgressTasks.length === 0
              ? (
                  <p className="mt-8 text-center text-sm text-text-tertiary">
                    暂无进行中的任务
                  </p>
                )
              : (
                  <div className="flex flex-col gap-2">
                    {inProgressTasks.map(task => (
                      <TaskItem
                        key={task.id}
                        task={task}
                        onClick={handleTaskClick}
                        onRename={renameTask}
                        onDelete={deleteTask}
                      />
                    ))}
                  </div>
                )}
          </>
        )}
        {activeTab === 'completed' && (
          <>
            {completedTasks.length === 0
              ? (
                  <p className="mt-8 text-center text-sm text-text-tertiary">
                    暂无已完成的任务
                  </p>
                )
              : (
                  <div className="flex flex-col gap-2">
                    {completedTasks.map(task => (
                      <TaskItem
                        key={task.id}
                        task={task}
                        onClick={handleTaskClick}
                        onRename={renameTask}
                        onDelete={deleteTask}
                      />
                    ))}
                  </div>
                )}
          </>
        )}
      </div>
    </div>
  )
}
