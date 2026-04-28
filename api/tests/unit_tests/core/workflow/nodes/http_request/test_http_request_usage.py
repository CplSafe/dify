import json
from types import SimpleNamespace

from graphon.enums import WorkflowNodeExecutionMetadataKey, WorkflowNodeExecutionStatus
from graphon.node_events import NodeRunResult

from core.workflow.nodes.http_request.node import DifyHttpRequestNode, apply_http_token_usage_to_result


class RetryableHttpNode(DifyHttpRequestNode):
    def __init__(self, *, node_data: SimpleNamespace, results: list[NodeRunResult]) -> None:
        self._node_data = node_data
        self._results = results
        self.run_count = 0

    def _run_once(self) -> NodeRunResult:
        result = self._results[min(self.run_count, len(self._results) - 1)]
        self.run_count += 1
        return result

    def _sleep_before_usage_retry(self) -> None:
        return None


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


def test_get_http_node_retries_terminal_response_until_usage_arrives() -> None:
    node_data = SimpleNamespace(
        method="get",
        get=lambda key, default=None: {
            "method": "get",
            "billing_config": {
                "enabled": True,
                "output_tokens_path": "usage.total_tokens",
            },
        }.get(key, default),
    )
    first_result = NodeRunResult(
        status=WorkflowNodeExecutionStatus.SUCCEEDED,
        outputs={
            "status_code": 200,
            "body": json.dumps({"id": "task-id", "status": "succeeded", "content": {"video_url": "https://example"}}),
            "headers": {},
            "files": [],
        },
    )
    second_result = NodeRunResult(
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
    node = RetryableHttpNode(node_data=node_data, results=[first_result, second_result])

    result = node._run()

    assert node.run_count == 2
    assert result.llm_usage.total_tokens == 324900
    assert result.outputs["usage"]["total_tokens"] == 324900
    assert result.process_data["usage"]["total_tokens"] == 324900


def test_post_http_node_does_not_retry_terminal_response_without_usage() -> None:
    node_data = SimpleNamespace(
        method="post",
        get=lambda key, default=None: {
            "method": "post",
            "billing_config": {
                "enabled": True,
                "output_tokens_path": "usage.total_tokens",
            },
        }.get(key, default),
    )
    result_without_usage = NodeRunResult(
        status=WorkflowNodeExecutionStatus.SUCCEEDED,
        outputs={
            "status_code": 200,
            "body": json.dumps({"id": "task-id", "status": "succeeded"}),
            "headers": {},
            "files": [],
        },
    )
    node = RetryableHttpNode(node_data=node_data, results=[result_without_usage])

    result = node._run()

    assert node.run_count == 1
    assert result.llm_usage.total_tokens == 0
