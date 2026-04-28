"""Workflow persistence layer for GraphEngine.

This layer mirrors the former ``WorkflowCycleManager`` responsibilities by
listening to ``GraphEngineEvent`` instances directly and persisting workflow
and node execution state via the injected repositories.

The design keeps domain persistence concerns inside the engine thread, while
allowing presentation layers to remain read-only observers of repository
state.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Union

from graphon.enums import (
    WorkflowExecutionStatus,
    WorkflowNodeExecutionMetadataKey,
    WorkflowNodeExecutionStatus,
    WorkflowType,
)

from core.app.entities.app_invoke_entities import AdvancedChatAppGenerateEntity, UserFrom, WorkflowAppGenerateEntity
from core.ops.entities.trace_entity import TraceTaskName
from core.ops.ops_trace_manager import TraceQueueManager, TraceTask
from core.repositories.factory import WorkflowExecutionRepository, WorkflowNodeExecutionRepository
from core.workflow.system_variables import SystemVariableKey
from core.workflow.variable_prefixes import SYSTEM_VARIABLE_NODE_ID
from core.workflow.workflow_run_outputs import project_node_outputs_for_workflow_run
from graphon.entities import WorkflowExecution, WorkflowNodeExecution
from graphon.graph_engine.layers import GraphEngineLayer
from graphon.graph_events import (
    GraphEngineEvent,
    GraphRunAbortedEvent,
    GraphRunFailedEvent,
    GraphRunPartialSucceededEvent,
    GraphRunPausedEvent,
    GraphRunStartedEvent,
    GraphRunSucceededEvent,
    NodeRunExceptionEvent,
    NodeRunFailedEvent,
    NodeRunPauseRequestedEvent,
    NodeRunRetryEvent,
    NodeRunStartedEvent,
    NodeRunSucceededEvent,
)
from graphon.node_events import NodeRunResult
from libs.datetime_utils import naive_utc_now


@dataclass(slots=True)
class PersistenceWorkflowInfo:
    """Static workflow metadata required for persistence."""

    workflow_id: str
    workflow_type: WorkflowType
    version: str
    graph_data: Mapping[str, Any]


@dataclass(slots=True)
class _NodeRuntimeSnapshot:
    """Lightweight cache to keep node metadata across event phases."""

    node_id: str
    title: str
    predecessor_node_id: str | None
    iteration_id: str | None
    loop_id: str | None
    created_at: datetime


class WorkflowPersistenceLayer(GraphEngineLayer):
    """GraphEngine layer that persists workflow and node execution state."""

    def __init__(
        self,
        *,
        application_generate_entity: Union[AdvancedChatAppGenerateEntity, WorkflowAppGenerateEntity],
        workflow_info: PersistenceWorkflowInfo,
        workflow_execution_repository: WorkflowExecutionRepository,
        workflow_node_execution_repository: WorkflowNodeExecutionRepository,
        trace_manager: TraceQueueManager | None = None,
    ) -> None:
        super().__init__()
        self._application_generate_entity = application_generate_entity
        self._workflow_info = workflow_info
        self._workflow_execution_repository = workflow_execution_repository
        self._workflow_node_execution_repository = workflow_node_execution_repository
        self._trace_manager = trace_manager

        self._workflow_execution: WorkflowExecution | None = None
        self._node_execution_cache: dict[str, WorkflowNodeExecution] = {}
        self._node_snapshots: dict[str, _NodeRuntimeSnapshot] = {}
        self._node_sequence: int = 0
        # Independent counter for HTTP-node tokens. graphon's runtime
        # `total_tokens` accumulator misses HTTP nodes intermittently in
        # loop contexts (root cause unclear — likely event-ordering race
        # between graph engine and layer notification). We mirror the same
        # add_tokens calls into this counter so completion stats can fall
        # back to it when runtime_state lost the data.
        self._http_tokens_accumulated: int = 0
        # Per-run cumulative billing amount for HTTP nodes, computed at
        # extraction time using each node's own ``billing_price_per_k_tokens``.
        # Keeps the bookkeeping simple — no averaging across nodes, no second
        # pass over outputs at billing time. ``_bill_workflow_run`` consumes
        # this and the LLM token total separately.
        from decimal import Decimal as _Decimal

        self._http_billing_amount_accumulated: _Decimal = _Decimal(0)

    # ------------------------------------------------------------------
    # GraphEngineLayer lifecycle
    # ------------------------------------------------------------------
    def on_graph_start(self) -> None:
        from decimal import Decimal as _Decimal

        self._workflow_execution = None
        self._node_execution_cache.clear()
        self._node_snapshots.clear()
        self._node_sequence = 0
        self._http_tokens_accumulated = 0
        self._http_billing_amount_accumulated = _Decimal(0)

    def on_event(self, event: GraphEngineEvent) -> None:
        if isinstance(event, GraphRunStartedEvent):
            self._handle_graph_run_started()
            return

        if isinstance(event, GraphRunSucceededEvent):
            self._handle_graph_run_succeeded(event)
            return

        if isinstance(event, GraphRunPartialSucceededEvent):
            self._handle_graph_run_partial_succeeded(event)
            return

        if isinstance(event, GraphRunFailedEvent):
            self._handle_graph_run_failed(event)
            return

        if isinstance(event, GraphRunAbortedEvent):
            self._handle_graph_run_aborted(event)
            return

        if isinstance(event, GraphRunPausedEvent):
            self._handle_graph_run_paused(event)
            return

        if isinstance(event, NodeRunRetryEvent):
            self._handle_node_retry(event)
            return

        if isinstance(event, NodeRunStartedEvent):
            self._handle_node_started(event)
            return

        if isinstance(event, NodeRunSucceededEvent):
            self._handle_node_succeeded(event)
            return

        if isinstance(event, NodeRunFailedEvent):
            self._handle_node_failed(event)
            return

        if isinstance(event, NodeRunExceptionEvent):
            self._handle_node_exception(event)
            return

        if isinstance(event, NodeRunPauseRequestedEvent):
            self._handle_node_pause_requested(event)

    def on_graph_end(self, error: Exception | None) -> None:
        return

    # ------------------------------------------------------------------
    # Graph-level handlers
    # ------------------------------------------------------------------
    def _handle_graph_run_started(self) -> None:
        execution_id = self._get_execution_id()
        workflow_execution = WorkflowExecution.new(
            id_=execution_id,
            workflow_id=self._workflow_info.workflow_id,
            workflow_type=self._workflow_info.workflow_type,
            workflow_version=self._workflow_info.version,
            graph=self._workflow_info.graph_data,
            inputs=self._prepare_workflow_inputs(),
            started_at=naive_utc_now(),
        )

        self._workflow_execution_repository.save(workflow_execution)
        self._workflow_execution = workflow_execution

    def _handle_graph_run_succeeded(self, event: GraphRunSucceededEvent) -> None:
        execution = self._get_workflow_execution()
        execution.outputs = event.outputs
        execution.status = WorkflowExecutionStatus.SUCCEEDED
        self._populate_completion_statistics(execution)

        self._workflow_execution_repository.save(execution)
        self._enqueue_trace_task(execution)
        self._bill_workflow_run(execution)

    def _handle_graph_run_partial_succeeded(self, event: GraphRunPartialSucceededEvent) -> None:
        execution = self._get_workflow_execution()
        execution.outputs = event.outputs
        execution.status = WorkflowExecutionStatus.PARTIAL_SUCCEEDED
        execution.exceptions_count = event.exceptions_count
        self._populate_completion_statistics(execution)

        self._workflow_execution_repository.save(execution)
        self._enqueue_trace_task(execution)
        self._bill_workflow_run(execution)

    def _handle_graph_run_failed(self, event: GraphRunFailedEvent) -> None:
        execution = self._get_workflow_execution()
        execution.status = WorkflowExecutionStatus.FAILED
        execution.error_message = event.error
        execution.exceptions_count = event.exceptions_count
        self._populate_completion_statistics(execution)

        self._fail_running_node_executions(error_message=event.error)
        self._workflow_execution_repository.save(execution)
        self._enqueue_trace_task(execution)
        self._bill_workflow_run(execution)

    def _handle_graph_run_aborted(self, event: GraphRunAbortedEvent) -> None:
        execution = self._get_workflow_execution()
        execution.status = WorkflowExecutionStatus.STOPPED
        execution.error_message = event.reason or "Workflow execution aborted"
        self._populate_completion_statistics(execution)

        self._fail_running_node_executions(error_message=execution.error_message or "")
        self._workflow_execution_repository.save(execution)
        self._enqueue_trace_task(execution)
        self._bill_workflow_run(execution)

    def _handle_graph_run_paused(self, event: GraphRunPausedEvent) -> None:
        execution = self._get_workflow_execution()
        execution.status = WorkflowExecutionStatus.PAUSED
        execution.outputs = event.outputs
        self._populate_completion_statistics(execution, update_finished=False)

        self._workflow_execution_repository.save(execution)

    # ------------------------------------------------------------------
    # Node-level handlers
    # ------------------------------------------------------------------
    def _handle_node_started(self, event: NodeRunStartedEvent) -> None:
        execution = self._get_workflow_execution()

        metadata = {
            WorkflowNodeExecutionMetadataKey.ITERATION_ID: event.in_iteration_id,
            WorkflowNodeExecutionMetadataKey.LOOP_ID: event.in_loop_id,
        }

        domain_execution = WorkflowNodeExecution(
            id=event.id,
            node_execution_id=event.id,
            workflow_id=execution.workflow_id,
            workflow_execution_id=execution.id_,
            predecessor_node_id=event.predecessor_node_id,
            index=self._next_node_sequence(),
            node_id=event.node_id,
            node_type=event.node_type,
            title=event.node_title,
            status=WorkflowNodeExecutionStatus.RUNNING,
            metadata=metadata,
            created_at=event.start_at,
        )

        self._node_execution_cache[event.id] = domain_execution
        self._workflow_node_execution_repository.save(domain_execution)

        snapshot = _NodeRuntimeSnapshot(
            node_id=event.node_id,
            title=event.node_title,
            predecessor_node_id=event.predecessor_node_id,
            iteration_id=event.in_iteration_id,
            loop_id=event.in_loop_id,
            created_at=event.start_at,
        )
        self._node_snapshots[event.id] = snapshot

    def _handle_node_retry(self, event: NodeRunRetryEvent) -> None:
        domain_execution = self._get_node_execution(event.id)
        domain_execution.status = WorkflowNodeExecutionStatus.RETRY
        domain_execution.error = event.error
        self._workflow_node_execution_repository.save(domain_execution)
        self._workflow_node_execution_repository.save_execution_data(domain_execution)

    def _handle_node_succeeded(self, event: NodeRunSucceededEvent) -> None:
        domain_execution = self._get_node_execution(event.id)
        self._update_node_execution(
            domain_execution,
            event.node_run_result,
            WorkflowNodeExecutionStatus.SUCCEEDED,
            finished_at=event.finished_at,
        )
        # Extract tokens from HTTP request node response body when token_field_name is configured
        if event.node_type == "http-request":
            self._extract_http_node_tokens(event)

    def _handle_node_failed(self, event: NodeRunFailedEvent) -> None:
        domain_execution = self._get_node_execution(event.id)
        self._update_node_execution(
            domain_execution,
            event.node_run_result,
            WorkflowNodeExecutionStatus.FAILED,
            error=event.error,
            finished_at=event.finished_at,
        )

    def _handle_node_exception(self, event: NodeRunExceptionEvent) -> None:
        domain_execution = self._get_node_execution(event.id)
        self._update_node_execution(
            domain_execution,
            event.node_run_result,
            WorkflowNodeExecutionStatus.EXCEPTION,
            error=event.error,
            finished_at=event.finished_at,
        )

    def _handle_node_pause_requested(self, event: NodeRunPauseRequestedEvent) -> None:
        domain_execution = self._get_node_execution(event.id)
        self._update_node_execution(
            domain_execution,
            event.node_run_result,
            WorkflowNodeExecutionStatus.PAUSED,
            error="",
            update_outputs=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _extract_http_node_tokens(self, event: NodeRunSucceededEvent) -> None:
        """Extract token count + billing amount from an HTTP node's response body.

        When an HTTP node is configured with ``token_field_name`` (e.g.
        ``usage.total_tokens``) and ``billing_price_per_k_tokens``, parse the
        response body JSON, walk the dot-separated path to read the integer
        token value, accumulate tokens into ``graph_runtime_state``, and
        accumulate ``tokens * price / 1000`` into
        ``self._http_billing_amount_accumulated`` for the run-level deduction.

        Every silent skip is logged at INFO with a stable prefix so production
        runs can be traced from logs alone — the body of an HTTP polling loop
        emits dozens of these per run, but only one terminal call should ever
        write tokens, so the noise is bounded.
        """
        import json
        import logging
        from decimal import Decimal, InvalidOperation

        logger = logging.getLogger(__name__)

        run_id = getattr(self._workflow_execution, "id_", None) or "?"
        loop_id = getattr(event, "in_loop_id", None)
        token_field_name: str = ""
        try:
            graph_data = self._workflow_info.graph_data or {}
            nodes = graph_data.get("nodes", [])
            node_config: dict[str, Any] | None = None
            for n in nodes:
                if n.get("id") == event.node_id:
                    node_config = n.get("data", {})
                    break

            if not node_config:
                logger.info(
                    "HTTP-USAGE skip[no-graph-config] run=%s node=%s loop=%s graph_nodes=%d",
                    run_id,
                    event.node_id,
                    loop_id,
                    len(nodes),
                )
                return

            token_field_name = (node_config.get("token_field_name") or "").strip()
            if not token_field_name:
                # Node intentionally not configured for billing — log once per
                # event so we can confirm the config reaches this path at all.
                logger.info(
                    "HTTP-USAGE skip[no-token-field] run=%s node=%s loop=%s",
                    run_id,
                    event.node_id,
                    loop_id,
                )
                return

            outputs = event.node_run_result.outputs or {}
            body_raw = outputs.get("body")
            if body_raw is None or body_raw == "":
                logger.info(
                    "HTTP-USAGE skip[empty-body] run=%s node=%s loop=%s outputs_keys=%s",
                    run_id,
                    event.node_id,
                    loop_id,
                    list(outputs.keys()),
                )
                return

            if isinstance(body_raw, str):
                try:
                    body = json.loads(body_raw)
                except json.JSONDecodeError:
                    logger.info(
                        "HTTP-USAGE skip[body-not-json] run=%s node=%s loop=%s body_head=%s",
                        run_id,
                        event.node_id,
                        loop_id,
                        body_raw[:120],
                    )
                    return
            elif isinstance(body_raw, dict):
                body = body_raw
            else:
                logger.info(
                    "HTTP-USAGE skip[body-bad-type] run=%s node=%s loop=%s type=%s",
                    run_id,
                    event.node_id,
                    loop_id,
                    type(body_raw).__name__,
                )
                return

            value: Any = body
            for key in token_field_name.split("."):
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    value = None
                    break

            if value is None:
                logger.info(
                    "HTTP-USAGE skip[path-miss] run=%s node=%s loop=%s field=%s body_keys=%s",
                    run_id,
                    event.node_id,
                    loop_id,
                    token_field_name,
                    list(body.keys()) if isinstance(body, dict) else type(body).__name__,
                )
                return

            try:
                tokens = int(value)
            except (TypeError, ValueError):
                logger.info(
                    "HTTP-USAGE skip[value-not-int] run=%s node=%s loop=%s field=%s value=%r",
                    run_id,
                    event.node_id,
                    loop_id,
                    token_field_name,
                    value,
                )
                return

            if tokens <= 0:
                logger.info(
                    "HTTP-USAGE skip[non-positive] run=%s node=%s loop=%s tokens=%d",
                    run_id,
                    event.node_id,
                    loop_id,
                    tokens,
                )
                return

            try:
                price_per_k = Decimal(str(node_config.get("billing_price_per_k_tokens") or "0"))
            except (InvalidOperation, ValueError):
                price_per_k = Decimal(0)
            amount = (Decimal(tokens) / Decimal(1000) * price_per_k).quantize(Decimal("0.000001"))

            state = getattr(self.graph_runtime_state, "_state", None) or self.graph_runtime_state
            before = getattr(state, "total_tokens", 0)
            state.add_tokens(tokens)
            after = getattr(state, "total_tokens", 0)
            self._http_tokens_accumulated += tokens
            self._http_billing_amount_accumulated += amount

            logger.info(
                "HTTP-USAGE applied run=%s node=%s loop=%s tokens=+%d price/k=%s amount=+%s "
                "runtime=%d→%d mirror_tokens=%d mirror_amount=%s",
                run_id,
                event.node_id,
                loop_id,
                tokens,
                str(price_per_k),
                str(amount),
                before,
                after,
                self._http_tokens_accumulated,
                str(self._http_billing_amount_accumulated),
            )
        except Exception as exc:
            logger.warning(
                "HTTP-USAGE error run=%s node=%s loop=%s field=%s: %s",
                run_id,
                event.node_id,
                loop_id,
                token_field_name,
                exc,
            )

    def _get_execution_id(self) -> str:
        workflow_execution_id = self._system_variables().get(SystemVariableKey.WORKFLOW_EXECUTION_ID)
        if not workflow_execution_id:
            raise ValueError("workflow_execution_id must be provided in system variables for pause/resume flows")
        return str(workflow_execution_id)

    def _prepare_workflow_inputs(self) -> Mapping[str, Any]:
        inputs = {**self._application_generate_entity.inputs}
        for field_name, value in self._system_variables().items():
            if field_name == SystemVariableKey.CONVERSATION_ID.value:
                # Conversation IDs are tied to the current session; omit them so persisted
                # workflow inputs stay reusable without binding future runs to this conversation.
                continue
            inputs[f"sys.{field_name}"] = value
        # Local import to avoid circular dependency during app bootstrapping.
        from core.workflow.workflow_entry import WorkflowEntry

        handled = WorkflowEntry.handle_special_values(inputs)
        return handled or {}

    def _get_workflow_execution(self) -> WorkflowExecution:
        if self._workflow_execution is None:
            raise ValueError("workflow execution not initialized")
        return self._workflow_execution

    def _get_node_execution(self, node_execution_id: str) -> WorkflowNodeExecution:
        if node_execution_id not in self._node_execution_cache:
            raise ValueError(f"Node execution not found for id={node_execution_id}")
        return self._node_execution_cache[node_execution_id]

    def _next_node_sequence(self) -> int:
        self._node_sequence += 1
        return self._node_sequence

    def _populate_completion_statistics(self, execution: WorkflowExecution, *, update_finished: bool = True) -> None:
        if update_finished:
            execution.finished_at = naive_utc_now()
        runtime_state = self.graph_runtime_state
        runtime_total = runtime_state.total_tokens
        # Detect the lost-token bug: if our HTTP-token mirror has more
        # tokens than runtime_state ended up with, runtime lost some
        # add_tokens writes (likely because another layer wrote
        # execution.total_tokens earlier). In that case rebuild the
        # final number from (runtime LLM portion) + (mirrored HTTP).
        if self._http_tokens_accumulated > 0 and runtime_total < self._http_tokens_accumulated:
            import logging

            _logger = logging.getLogger(__name__)
            _logger.warning(
                "runtime total_tokens=%d < mirrored HTTP tokens=%d; falling back to mirror+%d (runtime LLM portion)",
                runtime_total,
                self._http_tokens_accumulated,
                max(runtime_total - self._http_tokens_accumulated, 0),
            )
            # Treat any tokens already in runtime_total as LLM-side and
            # add the mirrored HTTP total. If runtime kept some HTTP
            # tokens, this would double-count, but the guard above
            # ensures runtime < mirror so that case is impossible here.
            execution.total_tokens = runtime_total + self._http_tokens_accumulated
        else:
            execution.total_tokens = runtime_total
        execution.total_steps = runtime_state.node_run_steps
        execution.outputs = execution.outputs or runtime_state.outputs
        execution.exceptions_count = runtime_state.exceptions_count

    def _update_node_execution(
        self,
        domain_execution: WorkflowNodeExecution,
        node_result: NodeRunResult,
        status: WorkflowNodeExecutionStatus,
        *,
        error: str | None = None,
        update_outputs: bool = True,
        finished_at: datetime | None = None,
    ) -> None:
        actual_finished_at = finished_at or naive_utc_now()
        snapshot = self._node_snapshots.get(domain_execution.id)
        start_at = snapshot.created_at if snapshot else domain_execution.created_at
        domain_execution.status = status
        domain_execution.finished_at = actual_finished_at
        domain_execution.elapsed_time = max((actual_finished_at - start_at).total_seconds(), 0.0)

        if error:
            domain_execution.error = error

        if update_outputs:
            projected_outputs = project_node_outputs_for_workflow_run(
                node_type=domain_execution.node_type,
                inputs=node_result.inputs,
                outputs=node_result.outputs,
            )
            domain_execution.update_from_mapping(
                inputs=node_result.inputs,
                process_data=node_result.process_data,
                outputs=projected_outputs,
                metadata=node_result.metadata,
            )

        self._workflow_node_execution_repository.save(domain_execution)
        self._workflow_node_execution_repository.save_execution_data(domain_execution)

    def _fail_running_node_executions(self, *, error_message: str) -> None:
        now = naive_utc_now()
        for execution in self._node_execution_cache.values():
            if execution.status == WorkflowNodeExecutionStatus.RUNNING:
                execution.status = WorkflowNodeExecutionStatus.FAILED
                execution.error = error_message
                execution.finished_at = now
                execution.elapsed_time = max((now - execution.created_at).total_seconds(), 0.0)
                self._workflow_node_execution_repository.save(execution)

    def _enqueue_trace_task(self, execution: WorkflowExecution) -> None:
        if not self._trace_manager:
            return

        conversation_id = self._system_variables().get(SystemVariableKey.CONVERSATION_ID.value)
        external_trace_id = None
        if isinstance(self._application_generate_entity, (WorkflowAppGenerateEntity, AdvancedChatAppGenerateEntity)):
            external_trace_id = self._application_generate_entity.extras.get("external_trace_id")

        trace_task = TraceTask(
            TraceTaskName.WORKFLOW_TRACE,
            workflow_execution=execution,
            conversation_id=conversation_id,
            user_id=self._trace_manager.user_id,
            external_trace_id=external_trace_id,
        )
        self._trace_manager.add_trace_task(trace_task)

    def _system_variables(self) -> Mapping[str, Any]:
        runtime_state = self.graph_runtime_state
        return runtime_state.variable_pool.get_by_prefix(SYSTEM_VARIABLE_NODE_ID)

    def _bill_workflow_run(self, execution: "WorkflowExecution") -> None:
        """Deduct billing for consumed tokens after any terminal workflow state.

        Two independent deductions:

        - **HTTP nodes**: amount already computed at extraction time using
          each node's own ``billing_price_per_k_tokens`` and accumulated in
          ``self._http_billing_amount_accumulated``. Deducted here in one
          call so the ledger gets a single ``BillingRecord`` per run.
        - **LLM nodes**: tokens accumulated by graphon's runtime
          ``total_tokens`` minus the HTTP share (which we mirror in
          ``self._http_tokens_accumulated``). Deducted at the platform
          default rate of 0.002 CNY/1k — LLM pricing is otherwise handled
          upstream and we don't double-bill.

        Runs for succeeded, partial-succeeded, failed, and aborted states so
        tokens consumed before an early termination are still billed.
        """
        import logging
        from decimal import Decimal

        from services.user_billing_service import UserBillingService

        logger = logging.getLogger(__name__)

        try:
            user_from = self._application_generate_entity.user_from
            tenant_id = (
                self._application_generate_entity.tenant_id or self._application_generate_entity.app_config.tenant_id
            )

            # Only bill platform accounts, not embedded end-users
            if user_from != UserFrom.ACCOUNT:
                return

            account_id = self._application_generate_entity.user_id
            run_id = str(execution.id_)

            http_tokens = self._http_tokens_accumulated
            http_amount = self._http_billing_amount_accumulated
            total_tokens = execution.total_tokens or 0
            llm_tokens = max(total_tokens - http_tokens, 0)

            logger.info(
                "BILL summary run=%s total_tokens=%d http_tokens=%d llm_tokens=%d http_amount=%s",
                run_id,
                total_tokens,
                http_tokens,
                llm_tokens,
                str(http_amount),
            )

            # 1) HTTP-node deduction: per-node priced amount, billed verbatim.
            if http_amount > Decimal(0):
                UserBillingService.deduct_for_workflow_run(
                    account_id=account_id,
                    tenant_id=tenant_id,
                    workflow_run_id=run_id,
                    total_tokens=http_tokens,
                    price_per_1k_tokens=(
                        (http_amount * Decimal(1000) / Decimal(http_tokens)) if http_tokens > 0 else Decimal(0)
                    ),
                )

            # 2) LLM-node deduction: platform-default rate over remaining tokens.
            if llm_tokens > 0:
                UserBillingService.deduct_for_workflow_run(
                    account_id=account_id,
                    tenant_id=tenant_id,
                    workflow_run_id=run_id,
                    total_tokens=llm_tokens,
                    price_per_1k_tokens=Decimal("0.002"),
                )
        except Exception:
            logger.exception("Failed to bill workflow run %s", execution.id_)
