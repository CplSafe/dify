import base64
import time
import uuid
from typing import IO, Optional

import requests
from dify_plugin import Speech2TextModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
)

SUBMIT_ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
ASR_RESOURCE_ID = "volc.bigasr.auc"
STATUS_OK = "20000000"
QUERY_MAX_ATTEMPTS = 30
QUERY_INTERVAL = 2
REQUEST_TIMEOUT = 30


class DoubaoVoiceSpeech2TextModel(Speech2TextModel):
    """Speech-to-text model backed by the Doubao (Volcengine) recording-file ASR API."""

    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        api_key = credentials.get("api_key")
        request_id = str(uuid.uuid4())
        audio_b64 = base64.b64encode(file.read()).decode("utf-8")
        audio_format = self._guess_format(getattr(file, "name", ""))

        self._submit(api_key, request_id, audio_b64, audio_format, user or "dify")
        return self._poll(api_key, request_id)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        try:
            audio_file_path = self._get_demo_file_path()
            with open(audio_file_path, "rb") as audio_file:
                self._invoke(model, credentials, audio_file)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _submit(
        self, api_key: str, request_id: str, audio_b64: str, audio_format: str, uid: str
    ) -> None:
        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": ASR_RESOURCE_ID,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
            "Content-Type": "application/json",
        }
        payload = {
            "user": {"uid": uid},
            "audio": {"data": audio_b64, "format": audio_format},
            "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True},
        }
        response = requests.post(
            SUBMIT_ENDPOINT, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        )
        self._raise_for_api_status(response)

    def _poll(self, api_key: str, request_id: str) -> str:
        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": ASR_RESOURCE_ID,
            "X-Api-Request-Id": request_id,
            "Content-Type": "application/json",
        }
        for _ in range(QUERY_MAX_ATTEMPTS):
            response = requests.post(QUERY_ENDPOINT, headers=headers, json={}, timeout=REQUEST_TIMEOUT)
            status = response.headers.get("X-Api-Status-Code", "")
            if status == STATUS_OK:
                return self._extract_text(response.json())
            if status in ("20000001", "20000002"):  # queued / processing
                time.sleep(QUERY_INTERVAL)
                continue
            self._raise_for_api_status(response)
        raise InvokeBadRequestError("Doubao ASR timed out waiting for the recognition result.")

    @staticmethod
    def _extract_text(body: dict) -> str:
        result = body.get("result")
        if isinstance(result, dict):
            return result.get("text", "")
        return result or ""

    @staticmethod
    def _guess_format(filename: str) -> str:
        if "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        return "wav"

    @staticmethod
    def _raise_for_api_status(response: requests.Response) -> None:
        status = response.headers.get("X-Api-Status-Code", "")
        if status == STATUS_OK:
            return
        message = response.headers.get("X-Api-Message", response.text)
        if status.startswith("4500") or status.startswith("4510"):
            raise InvokeAuthorizationError(f"[{status}] {message}")
        raise InvokeBadRequestError(f"[{status}] {message}")

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [requests.exceptions.ConnectionError, requests.exceptions.Timeout],
            InvokeBadRequestError: [requests.exceptions.HTTPError],
        }
