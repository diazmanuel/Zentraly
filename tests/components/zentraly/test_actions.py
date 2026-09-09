"""Tests for action failure categories and translated errors."""

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.actions import translate_action_errors
from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.device_classes.button.api import (
    ZentralyButtonApi,
)
from homeassistant.components.zentraly.device_classes.climate.api import (
    ZentralyClimateApi,
)
from homeassistant.components.zentraly.device_classes.number.api import (
    ZentralyNumberApi,
)
from homeassistant.components.zentraly.device_classes.select.api import (
    ZentralySelectApi,
)
from homeassistant.components.zentraly.device_classes.switch.api import (
    ZentralySwitchApi,
)
from homeassistant.components.zentraly.device_classes.types import SelectOperationMode
from homeassistant.components.zentraly.exceptions import (
    ZentralyApiError,
    ZentralyCommandRejectedError,
    ZentralyConnectionError,
    ZentralyInvalidResponseError,
    ZentralyValidationError,
)
from homeassistant.components.zentraly.models import ZentralyDevice
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.translation import async_get_translations

type Action = Callable[[ZentralyDevice], Coroutine[Any, Any, bool]]


@pytest.mark.parametrize(
    ("device_id", "action"),
    [
        pytest.param(
            "ZTEIM0100000001",
            lambda d: ZentralySwitchApi(d).async_set_power(True),
            id="switch",
        ),
        pytest.param(
            "ZTEIM0100000001",
            lambda d: ZentralyNumberApi(d).async_set_high_power_limit(1000),
            id="number",
        ),
        pytest.param(
            "ZTEIM0100000001",
            lambda d: ZentralySelectApi(d).async_set_operation_mode(
                SelectOperationMode.MANUAL
            ),
            id="select",
        ),
        pytest.param(
            "ZTTIN0100000001",
            lambda d: ZentralyClimateApi(d).async_set_target_temperature(22),
            id="climate",
        ),
        pytest.param(
            "ZTEIM0100000001",
            lambda d: ZentralyButtonApi(d).async_reset_device(),
            id="button",
        ),
    ],
)
@pytest.mark.parametrize(
    ("response", "error"),
    [
        pytest.param(None, ZentralyConnectionError, id="timeout"),
        pytest.param((1, {"status": 400}), ZentralyCommandRejectedError, id="rejected"),
        pytest.param((1, {}), ZentralyInvalidResponseError, id="missing-status"),
        pytest.param(
            (1, {"status": "200"}), ZentralyInvalidResponseError, id="invalid-status"
        ),
        pytest.param(
            (1, {"status": 200, "cmd": "unexpected", "rid": 1}),
            ZentralyInvalidResponseError,
            id="invalid-payload",
        ),
    ],
)
async def test_capability_action_errors(
    device_id: str,
    action: Action,
    response: tuple[int, dict[str, Any]] | None,
    error: type[ZentralyApiError],
) -> None:
    """Preserve the failure category through each capability API."""
    api = MagicMock(spec=ZentralyApi)
    api.async_execute_command.return_value = response
    device = create_device(api, device_id, "aabbccddeeff")
    with pytest.raises(error):
        await action(device)


@pytest.mark.parametrize(
    ("error", "ha_error", "key"),
    [
        pytest.param(
            ZentralyConnectionError,
            HomeAssistantError,
            "cannot_connect",
            id="connection",
        ),
        pytest.param(
            ZentralyInvalidResponseError,
            HomeAssistantError,
            "invalid_response",
            id="response",
        ),
        pytest.param(
            ZentralyCommandRejectedError,
            HomeAssistantError,
            "command_rejected",
            id="rejected",
        ),
        pytest.param(
            ZentralyValidationError,
            ServiceValidationError,
            "invalid_action",
            id="validation",
        ),
    ],
)
async def test_error_translation(
    error: type[ZentralyApiError], ha_error: type[HomeAssistantError], key: str
) -> None:
    """Expose translation metadata instead of model-specific technical text."""

    @translate_action_errors
    async def action() -> None:
        raise error("Technical protocol detail")

    with pytest.raises(ha_error) as exc:
        await action()
    assert exc.value.translation_domain == "zentraly"
    assert exc.value.translation_key == key
    assert isinstance(exc.value.__cause__, error)


async def test_model_validation() -> None:
    """A rejected model value is translated before any network write."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTTIN0100000001")
    api._connected = True
    device = create_device(api, api.device_id, "aabbccddeeff")
    with patch.object(api._connection, "async_send_command") as send:

        async def build_only(builder: Callable[[int], dict[str, Any]]) -> None:
            builder(1)

        send.side_effect = build_only
        with pytest.raises(ZentralyValidationError):
            await ZentralyClimateApi(device).async_set_target_temperature(100)


async def test_successful_action_builds_and_sends_command() -> None:
    """The action route preserves the original valid command and result."""
    api = MagicMock(spec=ZentralyApi)
    device = create_device(api, "ZTEIM0100000001", "aabbccddeeff")

    async def execute(
        builder: Callable[[int], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        command = builder(7)
        assert command["rid"] == 7
        assert command["mac"] == "aabbccddeeff"
        assert command["cmd"] == "zclCmd"
        return 7, {"cmd": "zclCmd", "rid": 7, "status": 200}

    api.async_execute_command.side_effect = execute
    assert await ZentralySwitchApi(device).async_set_power(True)


async def test_exception_translations(hass: HomeAssistant) -> None:
    """Exception messages and placeholders are available in generated translations."""
    translations = await async_get_translations(hass, "en", "exceptions", {"zentraly"})
    assert translations["component.zentraly.exceptions.invalid_action.message"] == (
        "The requested value or operation is not supported by this device."
    )
    assert (
        translations[
            "component.zentraly.exceptions.setup_cannot_connect.message"
        ].format(device_id="ZTTIN0100000001")
        == "Unable to connect to Zentraly device ZTTIN0100000001."
    )


@pytest.mark.parametrize(
    "stage",
    [
        pytest.param(0, id="power"),
        pytest.param(1, id="timer"),
        pytest.param(2, id="mode"),
    ],
)
async def test_timer_sequence_failure(stage: int) -> None:
    """Stop the timer sequence when any step returns an invalid payload."""
    responses = [
        (
            1,
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": 0, "val": 1}],
            },
        ),
        (2, {"cmd": "writeAttr", "rid": 2, "status": 200}),
        (3, {"cmd": "writeAttr", "rid": 3, "status": 200}),
    ]
    responses[stage] = (stage + 1, {"cmd": "unexpected", "status": 200})
    api = MagicMock(spec=ZentralyApi)
    api.async_execute_command.side_effect = responses
    device = create_device(api, "ZTEIM0100000001", "aabbccddeeff")
    with pytest.raises(ZentralyInvalidResponseError):
        await ZentralyNumberApi(device).async_set_timer(30)
    assert api.async_execute_command.await_count == stage + 1
