"""Workflow persistence layer for GraphEngine.

This layer mirrors the former ``WorkflowCycleManager`` responsibilities by
listening to ``GraphEngineEvent`` instances directly and persisting workflow
and node execution state via the injected repositories.

The design keeps domain persistence concerns inside the engine thread, while
allowing presentation layers to remain read-only observers of repository
state.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Union

from graphon.entities import WorkflowExecution, WorkflowNodeExecution
from graphon.enums import (
    WorkflowExecutionStatus,
    WorkflowNodeExecutionMetadataKey,
    WorkflowNodeExecutionStatus,
    WorkflowType,
)
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

from core.app.entities.app_invoke_entities import AdvancedChatAppGenerateEntity, UserFrom, WorkflowAppGenerateEntity
from core.ops.entities.trace_entity import TraceTaskName
from core.ops.ops_trace_manager import TraceQueueManager, TraceTask
from core.repositories.factory import WorkflowExecutionRepository, WorkflowNodeExecutionRepository
from core.workflow.system_variables import SystemVariableKey
from core.workflow.variable_prefixes import SYSTEM_VARIABLE_NODE_ID
from core.workflow.workflow_run_outputs import project_node_outputs_for_workflow_run
from libs.datetime_utils import naive_utc_now

logger = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # GraphEngineLayer lifecycle
    # ------------------------------------------------------------------
    def on_graph_start(self) -> None:
        self._workflow_execution = None
        self._node_execution_cache.clear()
        self._node_snapshots.clear()
        self._node_sequence = 0

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
        execution.total_tokens = runtime_state.total_tokens
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

    @staticmethod
    def _parse_decimal(value: Any, *, default: str = "0") -> Decimal:
        try:
            parsed = Decimal(str(value if value is not None else default).strip() or default)
        except Exception:
            return Decimal(default)
        return parsed if parsed > 0 else Decimal("0")

    @staticmethod
    def _coerce_token_value(value: Any) -> int:
        if value is None or isinstance(value, bool):
            return 0
        try:
            coerced = int(value)
        except Exception:
            try:
                coerced = int(float(str(value)))
            except Exception:
                return 0
        return max(coerced, 0)

    @staticmethod
    def _resolve_nested_value(data: Any, path: str | None) -> Any:
        if not path:
            return None

        current = data
        for segment in path.split("."):
            normalized = segment.strip()
            if not normalized:
                return None
            if isinstance(current, Mapping):
                current = current.get(normalized)
                continue
            return None
        return current

    @classmethod
    def _extract_usage_total_tokens(cls, payload: Any) -> int:
        if not isinstance(payload, Mapping):
            return 0
        usage = payload.get("usage")
        if not isinstance(usage, Mapping):
            return 0

        total_tokens = cls._coerce_token_value(usage.get("total_tokens"))
        if total_tokens > 0:
            return total_tokens

        return cls._coerce_token_value(usage.get("prompt_tokens")) + cls._coerce_token_value(
            usage.get("completion_tokens")
        )

    @classmethod
    def _extract_legacy_http_tokens(cls, *, outputs: Any, node_data: Mapping[str, Any]) -> int:
        if not isinstance(outputs, Mapping):
            return 0

        token_field_name = str(node_data.get("token_field_name") or "").strip()
        if not token_field_name:
            billing_config = node_data.get("billing_config")
            if isinstance(billing_config, Mapping):
                token_field_name = str(billing_config.get("output_tokens_path") or "").strip()
        if not token_field_name:
            return 0

        body_raw = outputs.get("body")
        if isinstance(body_raw, str):
            try:
                body = json.loads(body_raw.strip()) if body_raw.strip() else {}
            except json.JSONDecodeError:
                return 0
        elif isinstance(body_raw, Mapping):
            body = body_raw
        else:
            return 0

        return cls._coerce_token_value(cls._resolve_nested_value(body, token_field_name))

    @classmethod
    def _resolve_node_billable_tokens(cls, *, node_execution: Any, node_data: Mapping[str, Any]) -> int:
        for attr_name in ("outputs", "outputs_dict", "process_data", "process_data_dict"):
            payload = getattr(node_execution, attr_name, None)
            tokens = cls._extract_usage_total_tokens(payload)
            if tokens > 0:
                return tokens

        metadata = getattr(node_execution, "metadata", None) or getattr(
            node_execution, "execution_metadata_dict", None
        )
        if isinstance(metadata, Mapping):
            tokens = cls._coerce_token_value(metadata.get(WorkflowNodeExecutionMetadataKey.TOTAL_TOKENS))
            if tokens > 0:
                return tokens

        return cls._extract_legacy_http_tokens(outputs=getattr(node_execution, "outputs", None), node_data=node_data)

    @classmethod
    def _resolve_node_price_per_1k(cls, node_data: Mapping[str, Any]) -> Decimal:
        legacy_price = cls._parse_decimal(node_data.get("billing_price_per_k_tokens"))
        if legacy_price > 0:
            return legacy_price

        billing_config = node_data.get("billing_config")
        if not isinstance(billing_config, Mapping):
            return Decimal("0")

        output_price = cls._parse_decimal(billing_config.get("output_price_per_thousand"))
        if output_price > 0:
            return output_price
        return cls._parse_decimal(billing_config.get("input_price_per_thousand"))

    def _resolve_workflow_billing(self, execution: "WorkflowExecution") -> tuple[int, Decimal]:
        """Return billable tokens and amount using node-level token prices.

        ``execution.total_tokens`` already contains standard GraphEngine usage
        such as LLM and HTTP ``llm_usage``. Billing must not re-add HTTP tokens
        from node bodies on top of that total. Instead, priced nodes contribute
        their own usage once, at their own configured price.
        """

        graph_data = self._workflow_info.graph_data or {}
        node_configs = graph_data.get("nodes", [])
        node_data_by_id = {
            str(node.get("id")): node.get("data", {})
            for node in node_configs
            if isinstance(node, Mapping) and isinstance(node.get("data"), Mapping)
        }

        billable_tokens = 0
        total_amount = Decimal("0")
        for node_execution in self._node_execution_cache.values():
            node_data = node_data_by_id.get(str(getattr(node_execution, "node_id", "")))
            if not isinstance(node_data, Mapping):
                continue

            price_per_1k = self._resolve_node_price_per_1k(node_data)
            if price_per_1k <= 0:
                continue

            node_tokens = self._resolve_node_billable_tokens(node_execution=node_execution, node_data=node_data)
            if node_tokens <= 0:
                continue

            billable_tokens += node_tokens
            total_amount += (Decimal(node_tokens) / Decimal(1000)) * price_per_1k

        if billable_tokens > 0:
            return billable_tokens, total_amount.quantize(Decimal("0.000001"))

        total_tokens = int(execution.total_tokens or 0)
        if total_tokens <= 0:
            return 0, Decimal("0")
        default_price = Decimal("0.002")
        return total_tokens, ((Decimal(total_tokens) / Decimal(1000)) * default_price).quantize(Decimal("0.000001"))

    def _bill_workflow_run(self, execution: "WorkflowExecution") -> None:
        """Deduct billing for consumed tokens after any terminal workflow state.

        This runs for succeeded, partial-succeeded, failed, and aborted runs so
        that tokens consumed before an early termination are still billed.
        Only bills for platform accounts (not end-users).
        """
        from services.user_billing_service import UserBillingService

        try:
            user_from = self._application_generate_entity.user_from
            tenant_id = (
                self._application_generate_entity.tenant_id
                or self._application_generate_entity.app_config.tenant_id
            )

            # Only bill platform accounts, not embedded end-users
            if user_from != UserFrom.ACCOUNT:
                return

            account_id = self._application_generate_entity.user_id
            total_tokens, total_amount = self._resolve_workflow_billing(execution)
            if total_tokens <= 0 or total_amount <= 0:
                return

            price_per_1k = (total_amount * Decimal(1000)) / Decimal(total_tokens)

            UserBillingService.deduct_for_workflow_run(
                account_id=account_id,
                tenant_id=tenant_id,
                workflow_run_id=str(execution.id_),
                total_tokens=total_tokens,
                price_per_1k_tokens=price_per_1k,
            )
        except Exception:
            logger.exception("Failed to bill workflow run %s", execution.id_)
