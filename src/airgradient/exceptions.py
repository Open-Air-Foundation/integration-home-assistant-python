"""Asynchronous Python client for AirGradient."""

from __future__ import annotations


class AirGradientError(Exception):
    """Generic exception."""


class AirGradientConnectionError(AirGradientError):
    """AirGradient connection exception."""


class AirGradientParseError(AirGradientError):
    """AirGradient parse exception."""


class AirGradientHttpError(AirGradientError):
    """Structured Local API V1 HTTP exception."""

    def __init__(  # noqa: PLR0913  # pylint: disable=too-many-arguments
        self,
        *,
        status: int,
        code: str | None = None,
        field: str | None = None,
        message: str | None = None,
        content_type: str = "",
        body: str = "",
    ) -> None:
        """Initialize a structured HTTP exception."""
        self.status = status
        self.code = code
        self.field = field
        self.message = message
        self.content_type = content_type
        self.body = body
        detail = message or code or f"HTTP {status}"
        super().__init__(detail)


class AirGradientBadRequestError(AirGradientHttpError):
    """The device rejected an invalid request."""


class AirGradientForbiddenError(AirGradientHttpError):
    """The device currently forbids the operation."""


class AirGradientNotSupportedError(AirGradientHttpError):
    """The device does not support the operation."""


class AirGradientBusyError(AirGradientHttpError):
    """The device cannot currently admit the operation."""


class AirGradientInternalError(AirGradientHttpError):
    """The device encountered an internal failure."""
