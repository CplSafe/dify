"""Reconstruct a VariablePool from a finished workflow run's node outputs.

When the user rewinds chatflow message M to node N, we want every node
upstream of N to behave as if it just executed — without actually
re-executing them. We do that by seeding the new run's `VariablePool`
with each ancestor node's persisted `outputs` plus any user-supplied
overrides.

This module is engine-agnostic: it takes a list of `WorkflowNodeExecution`
DB rows + an override map and produces a populated `VariablePool`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from graphon.runtime.variable_pool import VariablePool

logger = logging.getLogger(__name__)


def populate_pool_from_executions(
    pool: VariablePool,
    *,
    ancestor_executions: Iterable[Any],
    output_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
    """Seed `pool` with `(node_id, output_key) -> value` from each row.

    Args:
        pool: target VariablePool, mutated in place.
        ancestor_executions: rows from `workflow_node_executions`. Each
            row is expected to expose either `outputs_dict` (preferred) or
            an `outputs` JSON column. The row must also have a `node_id`.
        output_overrides: optional `{node_id: {key: value}}` map. When a
            node has an override, the override **fully replaces** the
            persisted outputs — partial merges are too easy to misinterpret
            in the chatflow UI ("did the user clear that field?").

    Returns:
        Number of (node_id, key) variables added to the pool.
    """
    overrides = dict(output_overrides or {})
    written = 0

    for row in ancestor_executions:
        node_id = getattr(row, "node_id", None)
        if not node_id:
            continue

        if node_id in overrides:
            outputs = dict(overrides[node_id])
        else:
            outputs = _coerce_outputs(row)

        if not outputs:
            continue

        for key, value in outputs.items():
            try:
                pool.add([node_id, key], value)
                written += 1
            except Exception:
                # A single bad output (e.g. unserialisable file ref) should
                # not poison the entire rerun — log and continue.
                logger.warning(
                    "skipping ancestor output: node=%s key=%s",
                    node_id,
                    key,
                    exc_info=True,
                )
    return written


def _coerce_outputs(row: Any) -> Mapping[str, Any]:
    """Best-effort fetch the outputs dict from a node execution row."""
    outputs = getattr(row, "outputs_dict", None)
    if isinstance(outputs, Mapping):
        return outputs
    raw = getattr(row, "outputs", None)
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return parsed
    return {}
