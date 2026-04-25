"""GraphEngine layer that pauses a chatflow run after any node finishes
whose canvas-side `allow_user_edit_input` or `allow_user_edit_output`
flag is set to True.

The pause itself is delegated to graphon's existing PauseCommand
infrastructure, so the rest of the lifecycle (state persistence via
`PauseStatePersistenceLayer`, resume via `human_input_service.enqueue_resume`)
just works without any other changes.

This is the engine half of CR1 — it lets users intervene mid-flow on
nodes they (the chatflow author) have explicitly marked as "user-editable",
which is the foundation the canvas runtime UI builds on.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from graphon.graph_engine.entities.commands import PauseCommand
from graphon.graph_engine.layers import GraphEngineLayer
from graphon.graph_events import GraphEngineEvent
from graphon.graph_events.node import NodeRunSucceededEvent

logger = logging.getLogger(__name__)

# Reasons string surfaced through the pause SSE event so the frontend can
# tell apart human-input pauses (which need a form) from author-marked
# editable-node pauses (which expose the canvas-runtime "继续 / 编辑后继续"
# affordance).
USER_EDIT_PAUSE_REASON_PREFIX = "user_edit:"


class UserEditPauseLayer(GraphEngineLayer):
    """Pause the chatflow whenever an editable-flagged node succeeds.

    Editable means either `allow_user_edit_input` or `allow_user_edit_output`
    is set to True on the node's canvas data. The flag lives in the
    workflow draft JSON (set via the rerun-permissions panel — see
    `web/app/components/workflow/nodes/_base/components/rerun-permissions/`).

    The layer keeps a snapshot of node flags built once at construction
    time so the on-event hot path stays cheap (single dict lookup).
    """

    def __init__(self, *, graph_dict: Mapping[str, Any]) -> None:
        super().__init__()
        self._editable_nodes = self._extract_editable_nodes(graph_dict)
        # Track which nodes we've already paused on for this run so a
        # re-entrant Succeeded event (e.g. iteration body completing
        # multiple times) doesn't issue back-to-back PauseCommands.
        self._paused_once: set[str] = set()

    @staticmethod
    def _extract_editable_nodes(
        graph_dict: Mapping[str, Any],
    ) -> dict[str, dict[str, bool]]:
        """Build {node_id: {'input': bool, 'output': bool}} for fast lookup."""
        out: dict[str, dict[str, bool]] = {}
        for node in graph_dict.get("nodes", []) or []:
            node_id = node.get("id")
            if not node_id:
                continue
            data = node.get("data") or {}
            allow_in = data.get("allow_user_edit_input") is True
            allow_out = data.get("allow_user_edit_output") is True
            if allow_in or allow_out:
                out[node_id] = {"input": allow_in, "output": allow_out}
        return out

    def on_graph_start(self) -> None:
        self._paused_once.clear()

    def on_event(self, event: GraphEngineEvent) -> None:
        if not isinstance(event, NodeRunSucceededEvent):
            return
        node_id = event.node_id
        if node_id in self._paused_once:
            return
        flags = self._editable_nodes.get(node_id)
        if not flags:
            return
        if self.command_channel is None:
            # Layer not yet bound — should never happen when invoked by
            # GraphEngine, but tolerate it instead of crashing the run.
            logger.warning(
                "UserEditPauseLayer received event before initialize(); "
                "skipping pause for node %s",
                node_id,
            )
            return
        # Encode which kinds are editable in the reason so the frontend
        # can render the right inline buttons without another round trip.
        kinds = ",".join(
            kind for kind in ("input", "output") if flags.get(kind, False)
        )
        reason = f"{USER_EDIT_PAUSE_REASON_PREFIX}{node_id}:{kinds}"
        self.command_channel.send_command(PauseCommand(reason=reason))
        self._paused_once.add(node_id)
        logger.info(
            "UserEditPauseLayer paused chatflow at node %s (kinds=%s)",
            node_id,
            kinds,
        )

    def on_graph_end(self, error: Exception | None) -> None:
        # Reset state so a layer instance reused across runs (shouldn't
        # happen today, but cheap insurance) doesn't leak.
        self._paused_once.clear()
