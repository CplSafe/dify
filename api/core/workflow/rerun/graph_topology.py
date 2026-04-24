"""Graph topology helpers for the rerun engine.

Given a workflow `graph_dict` and a target node N, compute the set of
upstream nodes whose outputs we need to seed into the new VariablePool.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def compute_ancestors(graph: Mapping[str, Any], target_node_id: str) -> set[str]:
    """Return the set of node ids that can reach `target_node_id`.

    Includes nodes reachable through any edge — branches the actual run
    didn't take are still considered ancestors when computing the pool
    seed, because their outputs may be referenced by downstream nodes via
    selectors. Filtering against actually-executed rows is done by the
    caller using `workflow_node_executions`.

    Args:
        graph: `{nodes: [...], edges: [...]}` from `Workflow.graph_dict`.
        target_node_id: the rewind target. Returned set excludes the
            target itself.
    """
    edges = graph.get("edges", []) or []
    # Reverse adjacency: parent -> children, we need child -> parents
    incoming: dict[str, set[str]] = {}
    for edge in edges:
        src = edge.get("source")
        dst = edge.get("target")
        if not src or not dst:
            continue
        incoming.setdefault(dst, set()).add(src)

    ancestors: set[str] = set()
    stack = [target_node_id]
    while stack:
        cur = stack.pop()
        for parent in incoming.get(cur, ()):
            if parent in ancestors or parent == target_node_id:
                continue
            ancestors.add(parent)
            stack.append(parent)
    return ancestors


def find_downstream_node(graph: Mapping[str, Any], source_node_id: str) -> str | None:
    """Return the first downstream node id of `source_node_id`.

    Used when the user edits the *output* of a node — we start the rerun
    at the next node, treating the edited output as upstream context.

    For nodes with multiple outgoing edges (e.g. if-else), we pick the
    first edge in declaration order. Callers wanting branching control
    should bail out with a clearer error rather than rely on this.
    """
    edges = graph.get("edges", []) or []
    for edge in edges:
        if edge.get("source") == source_node_id:
            target = edge.get("target")
            if isinstance(target, str):
                return target
    return None


def is_node_inside_loop_or_iteration(
    graph: Mapping[str, Any], node_id: str
) -> bool:
    """True when the node sits inside a Loop or Iteration container.

    MVP rerun policy: only top-level nodes can be rewind targets — see
    docs/plans/2026-04-25-chatflow-node-rerun.md for the reasoning.
    """
    nodes = graph.get("nodes", []) or []
    for node in nodes:
        if node.get("id") != node_id:
            continue
        data = node.get("data", {}) or {}
        # Dify marks loop/iteration child nodes with these flags.
        if data.get("isInLoop") or data.get("isInIteration"):
            return True
        if data.get("loop_id") or data.get("iteration_id"):
            return True
        # Nodes nested inside container also have a parentId in graphon.
        if node.get("parentId"):
            return True
        return False
    return False
