import base64
import json
from collections.abc import Generator
from typing import Optional

import httpx
from dify_plugin import TTSModel
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
)

TTS_ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
TTS_RESOURCE_ID = "volc.service_type.10029"
DEFAULT_SAMPLE_RATE = 24000
REQUEST_TIMEOUT = 60


class DoubaoVoiceText2SpeechModel(TTSModel):
    """Text-to-speech model backed by the Doubao (Volcengine) V3 unidirectional API."""

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> Generator[bytes, None, None]:
        word_limit = self._get_model_word_limit(model, credentials) or 1000
        if len(content_text) > word_limit:
            sentences = self._split_text_into_sentences(content_text, max_length=word_limit)
        else:
            sentences = [content_text.strip()]

        speaker = voice or self._get_model_default_voice(model, credentials)
        uid = user or tenant_id
        for sentence in sentences:
            if not sentence:
                continue
            yield from self._synthesize_sentence(credentials, sentence, speaker, uid)

    def validate_credentials(self, model: str, credentials: dict, user: Optional[str] = None) -> None:
        try:
            speaker = self._get_model_default_voice(model, credentials)
            for _ in self._synthesize_sentence(credentials, "测试", speaker, user or "validate"):
                break
        except InvokeError as ex:
            raise CredentialsValidateFailedError(str(ex))
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _synthesize_sentence(
        self, credentials: dict, content_text: str, voice: str, uid: str
    ) -> Generator[bytes, None, None]:
        api_key = credentials.get("api_key")
        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": TTS_RESOURCE_ID,
            "Content-Type": "application/json",
        }
        payload = {
            "user": {"uid": uid},
            "req_params": {
                "text": content_text,
                "speaker": voice,
                "audio_params": {"format": "mp3", "sample_rate": DEFAULT_SAMPLE_RATE},
            },
        }

        with httpx.stream(
            "POST", TTS_ENDPOINT, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        ) as response:
            if response.status_code in (401, 403):
                code, message = self._read_error(response.read().decode("utf-8", "replace"))
                raise InvokeAuthorizationError(f"[{code}] {message}")
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                # Success chunks carry a top-level `code`; errors nest it under `header`.
                code = chunk.get("code", chunk.get("header", {}).get("code"))
                if code not in (0, 20000000):
                    message = chunk.get("message") or chunk.get("header", {}).get("message", "unknown error")
                    raise self._to_invoke_error(code, message)
                data = chunk.get("data")
                if data:
                    yield base64.b64decode(data)

    @staticmethod
    def _read_error(text: str) -> tuple[object, str]:
        try:
            header = json.loads(text.splitlines()[0]).get("header", {})
            return header.get("code", "unknown"), header.get("message", text[:200])
        except (json.JSONDecodeError, IndexError):
            return "unknown", text[:200]

    @staticmethod
    def _to_invoke_error(code: object, message: str) -> InvokeError:
        code_str = str(code)
        if code_str.startswith("4500") or code_str.startswith("4510"):
            return InvokeAuthorizationError(f"[{code}] {message}")
        if code_str.startswith("429") or code_str.startswith("5290"):
            return InvokeRateLimitError(f"[{code}] {message}")
        return InvokeBadRequestError(f"[{code}] {message}")

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [httpx.ConnectError, httpx.TimeoutException],
            InvokeBadRequestError: [httpx.HTTPStatusError, json.JSONDecodeError],
        }
