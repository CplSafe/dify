'use client'

import type { FC } from 'react'
import { useRerunController } from '@/app/components/base/chat/chat/answer/rerun-context'

type NodeRerunActionsProps = {
  nodeId: string
}

/**
 * Renders the "rerun from this node" affordance under a NodePanel.
 *
 * Visibility rules:
 * - Surface must provide a RerunController (creator chatflow debug only).
 * - Node must be present on the canvas (controller returns flags).
 * - At least one of `allow_user_edit_input/output` must be true on the node.
 *
 * M5 only emits the click — actual editor + dispatch land in M6/M7.
 */
const NodeRerunActions: FC<NodeRerunActionsProps> = ({ nodeId }) => {
  const controller = useRerunController()
  if (!controller)
    return null

  const flags = controller.getNodeRerunFlags(nodeId)
  if (!flags)
    return null
  if (!flags.allowEditInput && !flags.allowEditOutput)
    return null

  return (
    <div className="mt-1 flex items-center gap-2 border-t border-divider-subtle pt-2">
      <span className="system-2xs-medium-uppercase text-text-tertiary">
        重新运行
      </span>
      {flags.allowEditInput && (
        <button
          type="button"
          onClick={() => controller.onRerunFromNode(nodeId, 'input')}
          className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover"
          data-testid={`node-rerun-edit-input-${nodeId}`}
        >
          编辑输入并重跑
        </button>
      )}
      {flags.allowEditOutput && (
        <button
          type="button"
          onClick={() => controller.onRerunFromNode(nodeId, 'output')}
          className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover"
          data-testid={`node-rerun-edit-output-${nodeId}`}
        >
          编辑输出并重跑
        </button>
      )}
    </div>
  )
}

export default NodeRerunActions
