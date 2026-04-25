'use client'

import type { FC } from 'react'
import type { ChatflowRerunKind } from '@/service/debug'
import type { NodeTracing } from '@/types/workflow'
import { useCallback, useState } from 'react'
import { useRerunController } from '@/app/components/base/chat/chat/answer/rerun-context'
import RerunOverrideModal from './rerun-override-modal'

type NodeRerunActionsProps = {
  nodeInfo: NodeTracing
}

/**
 * Renders the "rerun from this node" affordance under a NodePanel.
 *
 * Visibility rules:
 * - Surface must provide a RerunController (creator chatflow debug only).
 * - Node must be present on the canvas (controller returns flags).
 * - At least one of `allow_user_edit_input/output` must be true on the node.
 *
 * On click opens RerunOverrideModal (M6) which persists the user's edit
 * via the M2 API and validates the rerun plan via M1. The actual streaming
 * dispatch lands in M7.
 */
const NodeRerunActions: FC<NodeRerunActionsProps> = ({ nodeInfo }) => {
  const controller = useRerunController()
  const [modalKind, setModalKind] = useState<ChatflowRerunKind | null>(null)

  const open = useCallback((kind: ChatflowRerunKind) => {
    setModalKind(kind)
    controller?.onRerunFromNode(nodeInfo.node_id, kind)
  }, [controller, nodeInfo.node_id])

  if (!controller)
    return null

  const flags = controller.getNodeRerunFlags(nodeInfo.node_id)
  if (!flags)
    return null
  if (!flags.allowEditInput && !flags.allowEditOutput)
    return null

  const initialData
    = modalKind === 'input'
      ? (typeof nodeInfo.inputs === 'object' && nodeInfo.inputs) || {}
      : (typeof nodeInfo.outputs === 'object' && nodeInfo.outputs) || {}

  return (
    <>
      <div className="mt-1 flex items-center gap-2 border-t border-divider-subtle pt-2">
        <span className="system-2xs-medium-uppercase text-text-tertiary">
          重新运行
        </span>
        {flags.allowEditInput && (
          <button
            type="button"
            onClick={() => open('input')}
            className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover"
            data-testid={`node-rerun-edit-input-${nodeInfo.node_id}`}
          >
            编辑输入并重跑
          </button>
        )}
        {flags.allowEditOutput && (
          <button
            type="button"
            onClick={() => open('output')}
            className="rounded-md border border-components-button-secondary-border bg-components-button-secondary-bg px-2 py-1 system-xs-medium text-text-secondary hover:bg-components-button-secondary-bg-hover"
            data-testid={`node-rerun-edit-output-${nodeInfo.node_id}`}
          >
            编辑输出并重跑
          </button>
        )}
      </div>
      {modalKind && (
        <RerunOverrideModal
          open={modalKind !== null}
          appId={controller.appId}
          messageId={controller.messageId}
          nodeId={nodeInfo.node_id}
          nodeTitle={nodeInfo.title || nodeInfo.node_id}
          kind={modalKind}
          initialData={initialData as Record<string, unknown>}
          onClose={() => setModalKind(null)}
        />
      )}
    </>
  )
}

export default NodeRerunActions
