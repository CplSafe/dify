'use client'
/* eslint-disable ts/no-explicit-any -- generic node-data shape */

import type { Node } from '@/app/components/workflow/types'
import { useCallback } from 'react'
import Switch from '@/app/components/base/switch'
import { useNodeDataUpdate } from '@/app/components/workflow/hooks'

/**
 * Per-node toggles that decide whether end-users (creator console) may
 * edit the node's input or output before re-running the chatflow.
 *
 * The values live in `node.data.allow_user_edit_input/output` (no schema
 * change — both flags are plain booleans on the node JSON). The backend
 * reads them in WorkflowRerunService.upsert_override (M4 will enforce).
 */
type Props = Pick<Node, 'id' | 'data'>

const RerunPermissionsPanel = ({ id, data }: Props) => {
  const { handleNodeDataUpdateWithSyncDraft } = useNodeDataUpdate()

  const allowInput = (data as any).allow_user_edit_input === true
  const allowOutput = (data as any).allow_user_edit_output === true
  // CR9: default true — author opts a node OUT of the canvas runtime
  // (e.g. internal glue nodes the end user shouldn't see). Hidden
  // nodes still execute; their edges are passed through to the next
  // visible successor in the runtime store.
  const showInRuntime = (data as any).show_in_canvas_runtime !== false

  const setFlag = useCallback(
    (
      key:
        | 'allow_user_edit_input'
        | 'allow_user_edit_output'
        | 'show_in_canvas_runtime',
      value: boolean,
    ) => {
      handleNodeDataUpdateWithSyncDraft({
        id,
        data: { [key]: value } as any,
      })
    },
    [id, handleNodeDataUpdateWithSyncDraft],
  )

  return (
    <div className="border-t-[0.5px] border-divider-regular px-4 pt-3 pb-2">
      <div className="mb-2 system-sm-semibold-uppercase text-text-secondary">
        画布运行时
      </div>
      <p className="mb-3 system-xs-regular text-text-tertiary">
        控制本节点在「运行画布」上的可见性与可编辑性。
      </p>
      <div className="flex h-9 items-center justify-between">
        <span className="system-sm-regular text-text-primary">
          在画布上显示
        </span>
        <Switch
          value={showInRuntime}
          onChange={v => setFlag('show_in_canvas_runtime', v)}
        />
      </div>
      <div className="flex h-9 items-center justify-between">
        <span className="system-sm-regular text-text-primary">
          允许编辑输入
        </span>
        <Switch
          value={allowInput}
          onChange={v => setFlag('allow_user_edit_input', v)}
        />
      </div>
      <div className="flex h-9 items-center justify-between">
        <span className="system-sm-regular text-text-primary">
          允许编辑输出
        </span>
        <Switch
          value={allowOutput}
          onChange={v => setFlag('allow_user_edit_output', v)}
        />
      </div>
    </div>
  )
}

export default RerunPermissionsPanel
