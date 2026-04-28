from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from graphon.enums import WorkflowNodeExecutionMetadataKey, WorkflowNodeExecutionStatus
from graphon.model_runtime.entities.llm_entities import LLMUsage
from graphon.model_runtime.utils.encoders import jsonable_encoder
from graphon.node_events import NodeRunResult
from graphon.nodes.http_request.node import HttpRequestNode

HTTP_NODE_OUTPUT_BODY_KEY = "body"
HTTP_NODE_BILLING_CONFIG_KEY = "billing_config"


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

        if isinstance(current, Sequence) and not isinstance(current, str):
            if not normalized.isdigit():
                return None
            index = int(normalized)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue

        return None

    return current


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


def _parse_decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value if value is not None else "0").strip() or "0")
    except Exception:
        return Decimal("0")
    return parsed if parsed > 0 else Decimal("0")


def _parse_http_body(outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    body = outputs.get(HTTP_NODE_OUTPUT_BODY_KEY)
    if isinstance(body, Mapping):
        return body
    if not isinstance(body, str):
        return {}

    body = body.strip()
    if not body:
        return {}

    try:
        parsed_body = json.loads(body)
    except Exception:
        return {}

    return parsed_body if isinstance(parsed_body, Mapping) else {}


def _get_node_data_value(node_data: Any, key: str) -> Any:
    if hasattr(node_data, "get"):
        return node_data.get(key)
    return getattr(node_data, key, None)


def _get_http_billing_config(node_data: Any) -> Mapping[str, Any]:
    raw_config = _get_node_data_value(node_data, HTTP_NODE_BILLING_CONFIG_KEY)
    return raw_config if isinstance(raw_config, Mapping) else {}


def _get_http_token_paths(node_data: Any) -> tuple[str, str]:
    raw_config = _get_http_billing_config(node_data)
    input_tokens_path = str(raw_config.get("input_tokens_path") or "").strip()
    output_tokens_path = str(raw_config.get("output_tokens_path") or "").strip()

    if not output_tokens_path:
        output_tokens_path = str(_get_node_data_value(node_data, "token_field_name") or "").strip()

    return input_tokens_path, output_tokens_path


def _get_http_output_price_per_1k(node_data: Any) -> Decimal:
    raw_config = _get_http_billing_config(node_data)
    price = _parse_decimal(raw_config.get("output_price_per_thousand"))
    if price > 0:
        return price
    return _parse_decimal(_get_node_data_value(node_data, "billing_price_per_k_tokens"))


def _extract_usage_from_http_result(*, result: NodeRunResult, node_data: Any) -> LLMUsage:
    if not isinstance(result.outputs, Mapping):
        return LLMUsage.empty_usage()

    input_tokens_path, output_tokens_path = _get_http_token_paths(node_data)
    if not input_tokens_path and not output_tokens_path:
        return LLMUsage.empty_usage()

    parsed_body = _parse_http_body(result.outputs)
    prompt_tokens = _coerce_token_value(_resolve_nested_value(parsed_body, input_tokens_path))
    completion_tokens = _coerce_token_value(_resolve_nested_value(parsed_body, output_tokens_path))
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens <= 0:
        return LLMUsage.empty_usage()

    output_price_per_1k = _get_http_output_price_per_1k(node_data)
    completion_price = (Decimal(completion_tokens) / Decimal(1000)) * output_price_per_1k

    return LLMUsage.from_metadata(
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "completion_unit_price": output_price_per_1k,
            "completion_price_unit": Decimal("0.001"),
            "completion_price": completion_price,
            "total_price": completion_price,
            "currency": "CNY",
        }
    )


def apply_http_token_usage_to_result(*, result: NodeRunResult, node_data: Any) -> None:
    """Expose HTTP response token usage through the same fields used by LLM nodes."""

    usage = _extract_usage_from_http_result(result=result, node_data=node_data)
    if usage.total_tokens <= 0:
        return

    usage_payload = jsonable_encoder(usage)
    result.llm_usage = usage
    result.outputs = {
        **dict(result.outputs),
        "usage": usage_payload,
    }
    result.process_data = {
        **dict(result.process_data),
        "usage": usage_payload,
    }
    result.metadata = {
        **dict(result.metadata),
        WorkflowNodeExecutionMetadataKey.TOTAL_TOKENS: usage.total_tokens,
        WorkflowNodeExecutionMetadataKey.TOTAL_PRICE: usage.total_price,
        WorkflowNodeExecutionMetadataKey.CURRENCY: usage.currency,
    }


class DifyHttpRequestNode(HttpRequestNode):
    def _run(self) -> NodeRunResult:
        result = super()._run()
        apply_http_token_usage_to_result(result=result, node_data=self.node_data)
        return result
