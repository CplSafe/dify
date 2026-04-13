'use client'

import { RiTaskLine } from '@remixicon/react'
import { useEffect, useRef, useState } from 'react'
import { useCreatorTasks } from '@/hooks/use-creator-tasks'
import TaskCenterDrawer from './drawer'

export default function TaskCenterButton() {
  const [open, setOpen] = useState(false)
  const { data, refresh } = useCreatorTasks()
  const drawerRef = useRef<HTMLDivElement>(null)

  // Close drawer on outside click
  useEffect(() => {
    if (!open)
      return
    const handler = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node))
        setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Initial badge count fetch
  useEffect(() => {
    refresh()
  }, [refresh])

  const inProgressCount = data.in_progress_count

  return (
    <>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className="relative rounded-lg p-2 text-text-tertiary hover:bg-state-base-hover hover:text-text-secondary"
        title="任务中心"
      >
        <RiTaskLine className="h-5 w-5" />
        {inProgressCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-[#F04438] text-[10px] font-bold text-white">
            {inProgressCount > 9 ? '9+' : inProgressCount}
          </span>
        )}
      </button>

      {/* Drawer panel */}
      {open && (
        <div
          ref={drawerRef}
          className="absolute top-full right-0 z-50 mt-1 w-80 overflow-hidden rounded-2xl border border-divider-subtle bg-components-panel-bg shadow-xl"
          style={{ maxHeight: 'calc(100vh - 80px)' }}
        >
          <TaskCenterDrawer onClose={() => setOpen(false)} />
        </div>
      )}
    </>
  )
}
