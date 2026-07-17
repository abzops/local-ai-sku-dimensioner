"""Bound multipart parsing before upload files are materialized by FastAPI."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request, status
from starlette.datastructures import FormData, Headers
from starlette.formparsers import MultiPartException, MultiPartParser

from backend.app.config import Settings
from backend.app.contracts import ImageView
from backend.app.errors import ApplicationError

MULTIPART_OVERHEAD_BYTES = 64 * 1024
NON_FILE_FIELD_LIMIT_BYTES = 1024


class UploadFileSizeExceeded(MultiPartException):
    """Signal that one file crossed the configured bound during parsing."""

    def __init__(self, field_name: str) -> None:
        super().__init__("Upload file exceeded its configured size limit.")
        self.field_name = field_name


class BoundedUploadMultiPartParser(MultiPartParser):
    """Apply a byte ceiling to file parts before they can fill temporary storage."""

    def __init__(
        self,
        headers: Headers,
        stream: AsyncGenerator[bytes, None],
        *,
        max_files: int,
        max_file_size_bytes: int,
    ) -> None:
        super().__init__(
            headers,
            stream,
            max_files=max_files,
            max_fields=0,
            max_part_size=NON_FILE_FIELD_LIMIT_BYTES,
        )
        self.max_file_size_bytes = max_file_size_bytes
        self._current_file_size = 0

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._current_file_size = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._current_file_size += end - start
            if self._current_file_size > self.max_file_size_bytes:
                raise UploadFileSizeExceeded(self._current_part.field_name)
        super().on_part_data(data, start, end)

    async def parse(self) -> FormData:
        try:
            return await super().parse()
        except Exception:
            for temporary_file in self._files_to_close_on_error:
                temporary_file.close()
            raise


async def parse_upload_form(request: Request, settings: Settings) -> FormData:
    """Return a bounded upload form or a sanitized structured request error."""
    content_type = request.headers.get("content-type", "")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as error:
            raise _malformed_multipart_error() from error
        maximum_request_bytes = (
            settings.max_upload_files_per_request
            * (settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES)
            + MULTIPART_OVERHEAD_BYTES
        )
        if declared_length > maximum_request_bytes:
            raise ApplicationError(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="UPLOAD_LIMIT_EXCEEDED",
                message="The multipart upload is too large.",
                recoverable=True,
                suggested_action="Reduce the number or size of the selected images.",
            )

    if not content_type:
        return FormData()
    if not content_type.lower().startswith("multipart/form-data"):
        raise _malformed_multipart_error()

    parser = BoundedUploadMultiPartParser(
        request.headers,
        request.stream(),
        max_files=settings.max_upload_files_per_request,
        max_file_size_bytes=settings.max_upload_bytes,
    )
    try:
        return await parser.parse()
    except UploadFileSizeExceeded as error:
        try:
            view = ImageView(error.field_name)
        except ValueError:
            view = None
        raise ApplicationError(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="FILE_TOO_LARGE",
            message="The image exceeds the maximum upload size.",
            recoverable=True,
            suggested_action=(
                f"Choose an image no larger than {settings.max_upload_mb} MiB."
            ),
            field=view.value if view is not None else None,
            view=view,
        ) from error
    except MultiPartException as error:
        if error.message.startswith("Too many files"):
            raise ApplicationError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="UPLOAD_LIMIT_EXCEEDED",
                message="The upload contains too many images.",
                recoverable=True,
                suggested_action=(
                    "Upload no more than "
                    f"{settings.max_upload_files_per_request} images at once."
                ),
            ) from error
        raise _malformed_multipart_error() from error
    except Exception as error:
        raise _malformed_multipart_error() from error


def _malformed_multipart_error() -> ApplicationError:
    return ApplicationError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="MALFORMED_MULTIPART",
        message="The multipart upload could not be parsed.",
        recoverable=True,
        suggested_action="Choose the images again and retry the upload.",
    )
