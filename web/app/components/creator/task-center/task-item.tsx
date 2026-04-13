'use client'

import type { CreatorTask, CreatorTaskStatus } from '@/service/creator-task'
import { RiCheckLine, RiCloseLine, RiLoader4Line, RiTimeLine } from '@remixicon/react'

type Props = {
  task: CreatorTask
  onClick: (task: CreatorTask) => void
}

const STATUS_CONFIG: Record<CreatorTaskStatus, { icon: React.ReactNode, label: string, color: string }> = {
  pending: {
    icon: <RiTimeLine className="h-4 w-4" />,
    label: '等待中',
    color: 'text-text-tertiary',
  },
  running: {
    icon: <RiLoader4Line className="h-4 w-4 animate-spin" />,
    label: '处理中',
    color: 'text-[#2970FF]',
  },
  waiting_input: {
    icon: <RiTimeLine className="h-4 w-4" />,
    label: '等待输入',
    color: 'text-[#F79009]',
  },
  completed: {
    icon: <RiCheckLine className="h-4 w-4" />,
    label: '已完成',
    color: 'text-[#12B76A]',
  },
  failed: {
    icon: <RiCloseLine className="h-4 w-4" />,
    label: '失败',
    color: 'text-[#F04438]',
  },
}

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1)
    return '刚刚'
  if (minutes < 60)
    return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24)
    return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30)
    return `${days}天前`
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

export default function TaskItem({ task, onClick }: Props) {
  const config = STATUS_CONFIG[task.status as CreatorTaskStatus] ?? STATUS_CONFIG.pending
  const isClickable = ['running', 'waiting_input', 'completed'].includes(task.status)
  const timeAgo = formatTimeAgo(task.created_at)

  return (
    <button
      type="button"
      className={[
        'w-full rounded-xl border border-divider-subtle bg-components-panel-bg px-4 py-3 text-left transition-colors',
        isClickable ? 'cursor-pointer hover:bg-state-base-hover' : 'cursor-default',
      ].join(' ')}
      onClick={() => isClickable && onClick(task)}
      disabled={!isClickable}
    >
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 shrink-0 ${config.color}`}>
          {config.icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-text-primary">
            {task.title || '创作任务'}
          </p>
          <p className="mt-0.5 text-xs text-text-tertiary">
            {config.label}
            {' '}
            ·
            {timeAgo}
          </p>
        </div>
      </div>
    </button>
  )
}
