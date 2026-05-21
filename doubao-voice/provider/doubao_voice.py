import logging
from collections.abc import Mapping

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class DoubaoVoiceProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """
        Validate provider credentials.

        Delegates to the TTS model, which performs the cheapest possible
        live request (a two-character synthesis) to verify the API Key.

        :param credentials: provider credentials defined in `provider_credential_schema`.
        """
        try:
            model_instance = self.get_model_instance(ModelType.TTS)
            model_instance.validate_credentials(model="Doubao-TTS", credentials=dict(credentials))
        except CredentialsValidateFailedError:
            raise
        except Exception:
            logger.exception("%s credentials validate failed", self.get_provider_schema().provider)
            raise
