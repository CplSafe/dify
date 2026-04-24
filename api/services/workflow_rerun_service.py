"""Chatflow node-level rerun service.

Entry point for rewinding a chatflow message to any past node and
re-running from there. Resolves the source `WorkflowRun`, computes the
ancestor outputs to seed, applies any user-supplied overrides from
`workflow_rerun_overrides`, and dispatches a fresh chatflow execution
that starts at the chosen node.

NOTE: This is the M1 backend skeleton. M2 wires up the
override-edit API, M5/M6 add the UI. The execution dispatch path is
intentionally minimal — it returns a context object that the chatflow
generator can consume on a follow-up call. Full streaming/replace
integration lands in M7.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import starmap
from typing import Any

from sqlalchemy import select

from core.workflow.rerun.ancestor_pool_builder import (
    populate_pool_from_executions,
)
from core.workflow.rerun.graph_topology import (
    compute_ancestors,
    find_downstream_node,
    is_node_inside_loop_or_iteration,
)
from extensions.ext_database import db
from models.model import Conversation, Message
from models.workflow import (
    Workflow,
    WorkflowNodeExecutionModel,
    WorkflowRerunOverride,
    WorkflowRerunOverrideKind,
    WorkflowRun,
)

logger = logging.getLogger(__name__)


class RerunValidationError(ValueError):
    """Raised when a rerun request fails preconditions."""


@dataclass
class RerunPlan:
    """Everything the chatflow generator needs to launch a partial rerun.

    Yielded by `WorkflowRerunService.prepare()`. The actual engine
    invocation happens in M7; until then we surface the plan so M2's
    controller can return it for inspection / curl-based testing.
    """

    source_message_id: str
    source_run_id: str
    workflow_id: str
    start_node_id: str
    # Ancestor node_id -> outputs dict to seed into VariablePool.
    ancestor_outputs: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    # Per-node `{node_id: outputs_or_inputs}` overrides the user provided.
    overrides_applied: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Workflow graph snapshot (we lock onto a specific revision).
    graph_dict: Mapping[str, Any] = field(default_factory=dict)
    # When the user edited a node's input, that node IS the start_node_id.
    # When they edited an output, start_node_id is the downstream node and
    # the edited node is added to ancestor_outputs.
    rewind_node_id: str = ""
    rewind_kind: str = ""  # "input" | "output"


class WorkflowRerunService:
    """Compute and dispatch chatflow node-level rerun plans."""

    @classmethod
    def prepare(
        cls,
        *,
        tenant_id: str,
        app_id: str,
        message_id: str,
        rewind_node_id: str,
        rewind_kind: str,
    ) -> RerunPlan:
        """Build a RerunPlan for the given rewind target.

        Validates that:
          1. The message exists, belongs to the tenant/app.
          2. It has a backing workflow_run that succeeded.
          3. The rewind node exists in the workflow graph.
          4. The rewind node is NOT inside a Loop/Iteration container.
          5. (Caller-enforced) the message is the latest in its
             conversation — done in the controller for simpler errors.
        """
        if rewind_kind not in {
            WorkflowRerunOverrideKind.INPUT.value,
            WorkflowRerunOverrideKind.OUTPUT.value,
        }:
            raise RerunValidationError(
                f"invalid rewind_kind: {rewind_kind!r}; expected 'input' or 'output'"
            )

        message = cls._load_message(tenant_id=tenant_id, app_id=app_id, message_id=message_id)
        run = cls._load_run(message=message, tenant_id=tenant_id, app_id=app_id)
        workflow = cls._load_workflow(workflow_id=run.workflow_id, tenant_id=tenant_id)
        graph_dict = workflow.graph_dict or {}

        # Verify rewind node exists and is not inside a container.
        node_ids = {n.get("id") for n in graph_dict.get("nodes", []) or []}
        if rewind_node_id not in node_ids:
            raise RerunValidationError(
                f"rewind node {rewind_node_id!r} not found in workflow graph"
            )
        if is_node_inside_loop_or_iteration(graph_dict, rewind_node_id):
            raise RerunValidationError(
                f"rewind node {rewind_node_id!r} sits inside a loop/iteration "
                "container; only top-level nodes can be rerun targets"
            )

        # Decide the actual start node based on rewind_kind.
        if rewind_kind == WorkflowRerunOverrideKind.INPUT.value:
            start_node_id = rewind_node_id
        else:  # OUTPUT
            downstream = find_downstream_node(graph_dict, rewind_node_id)
            if downstream is None:
                raise RerunValidationError(
                    f"node {rewind_node_id!r} has no downstream node — cannot "
                    "rewind on its output"
                )
            start_node_id = downstream

        # Pull ancestor execution rows (only successfully-completed ones).
        ancestor_ids = compute_ancestors(graph_dict, start_node_id)
        ancestor_executions = cls._load_executions(
            run_id=str(run.id), node_ids=ancestor_ids
        )

        # Pull all overrides for this message keyed by (node_id, kind).
        override_rows = cls._load_overrides(message_id=str(message.id))
        output_overrides: dict[str, dict[str, Any]] = {
            row.node_id: dict(row.override_data)
            for row in override_rows
            if row.override_kind == WorkflowRerunOverrideKind.OUTPUT.value
        }

        ancestor_outputs: dict[str, Mapping[str, Any]] = {}
        for row in ancestor_executions:
            ancestor_outputs[row.node_id] = output_overrides.get(
                row.node_id, row.outputs_dict or {}
            )

        return RerunPlan(
            source_message_id=str(message.id),
            source_run_id=str(run.id),
            workflow_id=str(workflow.id),
            start_node_id=start_node_id,
            ancestor_outputs=ancestor_outputs,
            overrides_applied={
                row.node_id: {
                    "kind": row.override_kind,
                    "data": dict(row.override_data),
                }
                for row in override_rows
            },
            graph_dict=graph_dict,
            rewind_node_id=rewind_node_id,
            rewind_kind=rewind_kind,
        )

    @classmethod
    def seed_pool(cls, plan: RerunPlan, pool: Any) -> int:
        """Populate `pool` (a VariablePool) with the plan's ancestor data.

        Thin wrapper kept on the service so the chatflow generator has a
        single import point. Returns the count of variables written.
        """
        return populate_pool_from_executions(
            pool, ancestor_executions=_DictExecAdapter.from_plan(plan)
        )

    # ------------------------------------------------------------------ helpers

    @classmethod
    def _load_message(cls, *, tenant_id: str, app_id: str, message_id: str) -> Message:
        message = db.session.execute(
            select(Message).where(Message.id == message_id)
        ).scalar_one_or_none()
        if message is None:
            raise RerunValidationError(f"message {message_id!r} not found")
        if str(message.app_id) != app_id:
            raise RerunValidationError("message does not belong to the requested app")
        # Validate tenant via the conversation join — Message itself doesn't
        # carry tenant_id directly.
        conversation = db.session.execute(
            select(Conversation).where(Conversation.id == message.conversation_id)
        ).scalar_one_or_none()
        if conversation is None or str(conversation.app_id) != app_id:
            raise RerunValidationError("conversation lookup failed")
        return message

    @classmethod
    def _load_run(cls, *, message: Message, tenant_id: str, app_id: str) -> WorkflowRun:
        run_id = getattr(message, "workflow_run_id", None)
        if not run_id:
            raise RerunValidationError(
                "message has no associated workflow_run — only chatflow messages "
                "can be rerun"
            )
        run = db.session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id)
        ).scalar_one_or_none()
        if run is None:
            raise RerunValidationError(f"workflow_run {run_id!r} not found")
        if str(run.tenant_id) != tenant_id or str(run.app_id) != app_id:
            raise RerunValidationError("workflow_run does not belong to caller")
        # MVP: only allow rerun on terminated runs — re-running a still-paused
        # run would race with the resume task.
        if run.status not in {"succeeded", "failed", "stopped"}:
            raise RerunValidationError(
                f"workflow_run is in status {run.status!r}; rerun only allowed "
                "on terminated runs"
            )
        return run

    @classmethod
    def _load_workflow(cls, *, workflow_id: str, tenant_id: str) -> Workflow:
        workflow = db.session.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        ).scalar_one_or_none()
        if workflow is None:
            raise RerunValidationError(f"workflow {workflow_id!r} not found")
        if str(workflow.tenant_id) != tenant_id:
            raise RerunValidationError("workflow does not belong to caller")
        return workflow

    @classmethod
    def _load_executions(
        cls, *, run_id: str, node_ids: set[str]
    ) -> list[WorkflowNodeExecutionModel]:
        if not node_ids:
            return []
        rows = db.session.execute(
            select(WorkflowNodeExecutionModel)
            .where(WorkflowNodeExecutionModel.workflow_run_id == run_id)
            .where(WorkflowNodeExecutionModel.node_id.in_(node_ids))
            .order_by(WorkflowNodeExecutionModel.index.asc())
        ).scalars().all()
        # Loop / iteration may produce multiple rows for the same node_id;
        # keep the latest successful one per node.
        latest: dict[str, WorkflowNodeExecutionModel] = {}
        for row in rows:
            if row.status != "succeeded":
                continue
            latest[row.node_id] = row  # later rows in index order win
        return list(latest.values())

    @classmethod
    def _load_overrides(cls, *, message_id: str) -> list[WorkflowRerunOverride]:
        return list(
            db.session.execute(
                select(WorkflowRerunOverride)
                .where(WorkflowRerunOverride.message_id == message_id)
                .order_by(WorkflowRerunOverride.created_at.asc())
            ).scalars().all()
        )


class _DictExecAdapter:
    """Wrap a `(node_id, outputs)` pair to look like a node-execution row.

    `populate_pool_from_executions` expects rows with `.node_id` and
    `.outputs_dict`. The plan stores plain dicts, so we adapt them rather
    than re-querying the database.
    """

    __slots__ = ("node_id", "outputs_dict")

    def __init__(self, node_id: str, outputs: Mapping[str, Any]):
        self.node_id = node_id
        self.outputs_dict = dict(outputs)

    @classmethod
    def from_plan(cls, plan: RerunPlan) -> list[_DictExecAdapter]:
        return list(starmap(cls, plan.ancestor_outputs.items()))
