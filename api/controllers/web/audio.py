import logging

from flask import request
from flask_restx import fields, marshal_with
from graphon.model_runtime.errors.invoke import InvokeError
from pydantic import BaseModel, field_validator
from werkzeug.exceptions import InternalServerError

import services
from controllers.web import web_ns
from controllers.web.error import (
    AppUnavailableError,
    AudioTooLargeError,
    CompletionRequestError,
    NoAudioUploadedError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderNotSupportSpeechToTextError,
    ProviderQuotaExceededError,
    UnsupportedAudioTypeError,
)
from controllers.web.wraps import WebApiResource
from core.errors.error import ModelCurrentlyNotSupportError, ProviderTokenNotInitError, QuotaExceededError
from libs.helper import uuid_value
from models.model import App
from services.audio_service import AudioService
from services.errors.audio import (
    AudioTooLargeServiceError,
    NoAudioUploadedServiceError,
    ProviderNotSupportSpeechToTextServiceError,
    UnsupportedAudioTypeServiceError,
)

from ..common.schema import register_schema_models


class TextToAudioPayload(BaseModel):
    message_id: str | None = None
    voice: str | None = None
    text: str | None = None
    streaming: bool | None = None

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return uuid_value(value)


register_schema_models(web_ns, TextToAudioPayload)

logger = logging.getLogger(__name__)


@web_ns.route("/audio-to-text")
class AudioApi(WebApiResource):
    audio_to_text_response_fields = {
        "text": fields.String,
    }

    @marshal_with(audio_to_text_response_fields)
    @web_ns.doc(
        description="语音转文字（ASR）。上传音频文件，返回识别后的文本内容。"
                    "通过 multipart/form-data 上传 file 字段。",
        responses={
            200: "成功，返回识别文本",
            400: "请求错误",
            401: "未认证",
            403: "无访问权限",
            413: "音频文件过大",
            415: "不支持的音频格式",
            500: "服务器内部错误",
        },
    )
    def post(self, app_model: App, end_user):
        """语音转文字"""
        file = request.files["file"]

        try:
            response = AudioService.transcript_asr(app_model=app_model, file=file, end_user=end_user)

            return response
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logger.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except ValueError as e:
            raise e
        except Exception as e:
            logger.exception("Failed to handle post request to AudioApi")
            raise InternalServerError()


@web_ns.route("/text-to-audio")
class TextApi(WebApiResource):
    @web_ns.expect(web_ns.models[TextToAudioPayload.__name__])
    @web_ns.doc(
        description="文字转语音（TTS）。传入消息 ID 或直接传入文本，"
                    "返回音频流（audio/mpeg）。可通过 voice 参数指定音色。",
        responses={
            200: "成功，返回音频流",
            400: "请求错误",
            401: "未认证",
            403: "无访问权限",
            500: "服务器内部错误",
        },
    )
    def post(self, app_model: App, end_user):
        """文字转语音"""
        try:
            payload = TextToAudioPayload.model_validate(web_ns.payload or {})

            message_id = payload.message_id
            text = payload.text
            voice = payload.voice
            response = AudioService.transcript_tts(
                app_model=app_model, text=text, voice=voice, end_user=end_user.external_user_id, message_id=message_id
            )

            return response
        except services.errors.app_model_config.AppModelConfigBrokenError:
            logger.exception("App model config broken.")
            raise AppUnavailableError()
        except NoAudioUploadedServiceError:
            raise NoAudioUploadedError()
        except AudioTooLargeServiceError as e:
            raise AudioTooLargeError(str(e))
        except UnsupportedAudioTypeServiceError:
            raise UnsupportedAudioTypeError()
        except ProviderNotSupportSpeechToTextServiceError:
            raise ProviderNotSupportSpeechToTextError()
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except ValueError as e:
            raise e
        except Exception as e:
            logger.exception("Failed to handle post request to TextApi")
            raise InternalServerError()
