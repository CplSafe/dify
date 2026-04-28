import json
from decimal import Decimal
from types import SimpleNamespace

from graphon.enums import WorkflowNodeExecutionMetadataKey, WorkflowNodeExecutionStatus
from graphon.node_events import NodeRunResult

from core.workflow.nodes.http_request.node import apply_http_token_usage_to_result


def test_applies_http_usage_to_llm_usage_shape() -> None:
    node_data = SimpleNamespace(
        get=lambda key, default=None: {
            "billing_config": {
                "enabled": True,
                "output_tokens_path": "usage.total_tokens",
            },
        }.get(key, default),
    )
    result = NodeRunResult(
        status=WorkflowNodeExecutionStatus.SUCCEEDED,
        outputs={
            "status_code": 200,
            "body": json.dumps({"usage": {"completion_tokens": 324900, "total_tokens": 324900}}),
            "headers": {},
            "files": [],
        },
    )

    apply_http_token_usage_to_result(result=result, node_data=node_data)

    assert result.llm_usage.total_tokens == 324900
    assert result.llm_usage.completion_tokens == 324900
    assert result.metadata[WorkflowNodeExecutionMetadataKey.TOTAL_TOKENS] == 324900
    assert result.outputs["usage"]["total_tokens"] == 324900
    assert result.process_data["usage"]["total_tokens"] == 324900


def test_applies_http_usage_from_mapping_body_and_token_strings() -> None:
    node_data = SimpleNamespace(
        get=lambda key, default=None: {
            "billing_config": {
                "enabled": True,
                "input_tokens_path": "usage.prompt_tokens",
                "output_tokens_path": "usage.completion_tokens",
            },
        }.get(key, default),
    )
    result = NodeRunResult(
        status=WorkflowNodeExecutionStatus.SUCCEEDED,
        outputs={
            "status_code": 200,
            "body": {"usage": {"prompt_tokens": "100", "completion_tokens": "324900.0"}},
            "headers": {},
            "files": [],
        },
    )

    apply_http_token_usage_to_result(result=result, node_data=node_data)

    assert result.llm_usage.prompt_tokens == 100
    assert result.llm_usage.completion_tokens == 324900
    assert result.llm_usage.total_tokens == 325000
    assert result.outputs["usage"]["total_tokens"] == 325000
    assert result.process_data["usage"]["total_tokens"] == 325000


def test_applies_http_usage_from_legacy_token_field_name() -> None:
    node_data = SimpleNamespace(
        token_field_name="usage.total_tokens",
        get=lambda key, default=None: {
            "token_field_name": "usage.total_tokens",
        }.get(key, default),
    )
    result = NodeRunResult(
        status=WorkflowNodeExecutionStatus.SUCCEEDED,
        outputs={
            "status_code": 200,
            "body": json.dumps(
                {
                    "id": "task-id",
                    "status": "succeeded",
                    "usage": {"completion_tokens": 324900, "total_tokens": 324900},
                }
            ),
            "headers": {},
            "files": [],
        },
    )

    apply_http_token_usage_to_result(result=result, node_data=node_data)

    assert result.llm_usage.total_tokens == 324900
    assert result.llm_usage.completion_tokens == 324900
    assert result.outputs["usage"]["total_tokens"] == 324900
    assert result.process_data["usage"]["total_tokens"] == 324900


def test_applies_http_usage_price_from_legacy_price_field() -> None:
    node_data = SimpleNamespace(
        token_field_name="usage.total_tokens",
        get=lambda key, default=None: {
            "token_field_name": "usage.total_tokens",
            "billing_price_per_k_tokens": "0.069",
        }.get(key, default),
    )
    result = NodeRunResult(
        status=WorkflowNodeExecutionStatus.SUCCEEDED,
        outputs={
            "status_code": 200,
            "body": json.dumps(
                {
                    "id": "task-id",
                    "status": "succeeded",
                    "content": {"video_url": "https://example"},
                    "usage": {"completion_tokens": 324900, "total_tokens": 324900},
                }
            ),
            "headers": {},
            "files": [],
        },
    )

    apply_http_token_usage_to_result(result=result, node_data=node_data)

    assert result.llm_usage.total_tokens == 324900
    assert result.llm_usage.total_price == Decimal("22.4181")
