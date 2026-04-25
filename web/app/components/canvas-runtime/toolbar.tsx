'use client'

import type { FC } from 'react'
import { RiAddLine, RiFullscreenLine, RiSubtractLine } from '@remixicon/react'
import { useReactFlow } from 'reactflow'

type ToolbarProps = {
  onSave?: () => void
  saveDisabled?: boolean
}

/**
 * Floating toolbar pinned to the top-right of the runtime canvas.
 * Save lives here (CR7 wires it). Zoom + fit-view come straight from
 * the ReactFlow instance so we don't need to mirror state.
 */
const RuntimeToolbar: FC<ToolbarProps> = ({ onSave, saveDisabled }) => {
  const { zoomIn, zoomOut, fitView } = useReactFlow()
  return (
    <div className="absolute top-4 right-4 z-20 flex items-center gap-1 rounded-xl border border-components-panel-border bg-components-panel-bg p-1 shadow-md">
      <button
        type="button"
        onClick={() => zoomOut({ duration: 200 })}
        className="flex h-7 w-7 items-center justify-center rounded-lg text-text-secondary hover:bg-state-base-hover"
        aria-label="缩小"
      >
        <RiSubtractLine className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => zoomIn({ duration: 200 })}
        className="flex h-7 w-7 items-center justify-center rounded-lg text-text-secondary hover:bg-state-base-hover"
        aria-label="放大"
      >
        <RiAddLine className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => fitView({ duration: 300, padding: 0.2 })}
        className="flex h-7 w-7 items-center justify-center rounded-lg text-text-secondary hover:bg-state-base-hover"
        aria-label="适应视图"
      >
        <RiFullscreenLine className="h-4 w-4" />
      </button>
      {onSave && (
        <>
          <div className="mx-1 h-5 w-px bg-divider-subtle" />
          <button
            type="button"
            onClick={onSave}
            disabled={saveDisabled}
            className="rounded-lg px-3 py-1 system-xs-medium text-text-primary hover:bg-state-base-hover disabled:cursor-not-allowed disabled:text-text-quaternary"
          >
            保存为画布
          </button>
        </>
      )}
    </div>
  )
}

export default RuntimeToolbar
