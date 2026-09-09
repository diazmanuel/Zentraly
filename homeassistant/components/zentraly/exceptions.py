"""Errors shared by Zentraly protocol and capability APIs."""


class ZentralyApiError(Exception):
    """Base Zentraly error."""

    translation_key = "action_failed"


class ZentralyAuthenticationError(ZentralyApiError):
    """Authentication was rejected."""


class ZentralyConnectionError(ZentralyApiError):
    """The device could not be reached."""

    translation_key = "cannot_connect"


class ZentralyInvalidResponseError(ZentralyApiError):
    """The device returned an invalid response."""

    translation_key = "invalid_response"


class ZentralyCommandRejectedError(ZentralyApiError):
    """The device rejected a command."""

    translation_key = "command_rejected"


class ZentralyValidationError(ZentralyApiError):
    """The requested value or operation is not supported by the model."""

    translation_key = "invalid_action"
