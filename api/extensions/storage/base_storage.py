"""Abstract interface for file storage implementations."""

from abc import ABC, abstractmethod
from collections.abc import Generator


class BaseStorage(ABC):
    """Interface for file storage."""

    @abstractmethod
    def save(self, filename: str, data: bytes):
        raise NotImplementedError

    @abstractmethod
    def load_once(self, filename: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def load_stream(self, filename: str) -> Generator:
        raise NotImplementedError

    @abstractmethod
    def download(self, filename: str, target_filepath: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, filename: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete(self, filename: str):
        raise NotImplementedError

    def scan(self, path, files=True, directories=False) -> list[str]:
        """
        Scan files and directories in the given path.
        This method is implemented only in some storage backends.
        If a storage backend doesn't support scanning, it will raise NotImplementedError.
        """
        raise NotImplementedError("This storage backend doesn't support scanning")

    def supports_presigned_url(self) -> bool:
        """Whether the backend can mint a time-bounded HTTPS download URL.

        Default False keeps backward compatibility: callers must check
        before invoking ``generate_presigned_url`` and fall back to
        ``load_once`` / multipart when this returns False.
        """
        return False

    def generate_presigned_url(self, filename: str, expires_in: int = 3600) -> str:
        """Generate a temporary download URL for ``filename``.

        Used by the publish-center to hand large videos to sau without
        streaming the bytes through the api process. Implementations:

        - AWS S3: ``boto3.client('s3').generate_presigned_url('get_object', ...)``
        - Aliyun OSS: ``bucket.sign_url('GET', key, expires_in)``

        Backends that don't natively support presigning leave the default
        NotImplementedError, and the caller falls back to multipart.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support presigned URLs"
        )

    def get_size(self, filename: str) -> int | None:
        """Return the byte size of an object without downloading it.

        Used by the publish-center to decide between presigned URL and
        multipart transport before reading the bytes. Returns ``None``
        when the backend can't cheaply answer (callers fall back to
        ``load_once`` then ``len``).
        """
        return None
