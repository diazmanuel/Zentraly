"""Translate Zentraly action errors at the Home Assistant boundary."""

from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .exceptions import ZentralyApiError, ZentralyValidationError


def translate_action_errors[**P, R](
    action: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, R]]:
    """Convert protocol errors without exposing technical details to the UI."""

    @wraps(action)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await action(*args, **kwargs)
        except ZentralyValidationError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key=err.translation_key
            ) from err
        except ZentralyApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=err.translation_key
            ) from err

    return wrapped
