'use client'

import type { CreatorTask, CreatorTaskStatus } from '@/service/creator-task'
import {
  RiCheckLine,
  RiCloseLine,
  RiDeleteBinLine,
  RiEditLine,
  RiLoader4Line,
  RiTimeLine,
} from '@remixicon/react'
import { useRef, useState } from 'react'

type Props = {
  task: CreatorTask
  onClick: (task: CreatorTask) => void
  onRename: (taskId: string, title: string) => Promise<boolean>
  onDelete: (taskId: string) => Promise<boolean>
}

const STATUS_CONFIG: Record<
  CreatorTaskStatus,
  { icon: React.ReactNode, label: string, color: string }
> = {
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
  const normalized
    = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : `${dateStr}Z`
  const diff = Date.now() - new Date(normalized).getTime()
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

export default function TaskItem({ task, onClick, onRename, onDelete }: Props) {
  const config
    = STATUS_CONFIG[task.status as CreatorTaskStatus] ?? STATUS_CONFIG.pending
  const isClickable = ['running', 'waiting_input', 'completed'].includes(
    task.status,
  )
  const timeAgo = formatTimeAgo(task.created_at)

  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState(task.title || '创作任务')
  const [saving, setSaving] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setEditValue(task.title || '创作任务')
    setIsEditing(true)
    setTimeout(() => inputRef.current?.select(), 0)
  }

  const commitEdit = async () => {
    const trimmed = editValue.trim()
    if (!trimmed || trimmed === (task.title || '创作任务')) {
      setIsEditing(false)
      return
    }
    setSaving(true)
    await onRename(task.id, trimmed)
    setSaving(false)
    setIsEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter')
      commitEdit()
    else if (e.key === 'Escape')
      setIsEditing(false)
  }

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation()
    await onDelete(task.id)
  }

  return (
    <div
      className={[
        'group w-full rounded-xl border border-divider-subtle bg-components-panel-bg px-4 py-3 text-left transition-colors',
        isClickable && !isEditing
          ? 'cursor-pointer hover:bg-state-base-hover'
          : 'cursor-default',
      ].join(' ')}
      onClick={() => !isEditing && isClickable && onClick(task)}
    >
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 shrink-0 ${config.color}`}>{config.icon}</span>
        <div className="min-w-0 flex-1">
          {isEditing
            ? (
                <input
                  ref={inputRef}
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onBlur={commitEdit}
                  disabled={saving}
                  maxLength={200}
                  className="w-full rounded border border-components-input-border-active bg-components-input-bg-normal px-1.5 py-0.5 text-sm text-text-primary outline-none"
                  onClick={e => e.stopPropagation()}
                />
              )
            : (
                <p className="truncate text-sm font-medium text-text-primary">
                  {task.title || '创作任务'}
                </p>
              )}
          <p className="mt-0.5 text-xs text-text-tertiary">
            {config.label}
            {' · '}
            {timeAgo}
          </p>
        </div>

        {/* Action buttons — visible on hover */}
        {!isEditing && (
          <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              type="button"
              title="重命名"
              onClick={startEdit}
              className="rounded p-1 text-text-tertiary hover:bg-state-base-hover hover:text-text-secondary"
            >
              <RiEditLine className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              title="删除"
              onClick={handleDelete}
              className="rounded p-1 text-text-tertiary hover:bg-state-destructive-hover hover:text-text-destructive"
            >
              <RiDeleteBinLine className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
