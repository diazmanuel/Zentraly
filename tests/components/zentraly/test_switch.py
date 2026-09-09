"""Tests for Zentraly switch actions."""

from contextlib import AbstractContextManager, nullcontext
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.zentraly.device_classes.switch.api import (
    ZentralySwitchApi,
)
from homeassistant.components.zentraly.device_classes.switch.capabilities import (
    SwitchCapability,
)
from homeassistant.components.zentraly.switch import ZentralySwitch
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.parametrize(
    ("action", "value"),
    [
        pytest.param("async_turn_on", True, id="on"),
        pytest.param("async_turn_off", False, id="off"),
    ],
)
@pytest.mark.parametrize(
    ("success", "expectation"),
    [
        pytest.param(True, nullcontext(), id="success"),
        pytest.param(False, pytest.raises(HomeAssistantError), id="failure"),
    ],
)
async def test_power_action(
    platform_device: MagicMock,
    action: str,
    value: bool,
    success: bool,
    expectation: AbstractContextManager,
) -> None:
    """Update the switch only after a successful power command."""
    api = MagicMock(spec=ZentralySwitchApi)
    api.async_get_power.return_value = not value
    api.async_set_power.return_value = success
    entity = ZentralySwitch(
        device=platform_device, switch_api=api, capability=SwitchCapability.POWER
    )
    await entity.async_update()
    with patch.object(entity, "async_write_ha_state"), expectation:
        await getattr(entity, action)()
    assert entity.is_on == (success == value)
    api.async_set_power.assert_awaited_once_with(value)


async def test_disconnected_action(platform_device: MagicMock) -> None:
    """Do not send a power command through a disconnected gateway."""
    platform_device.connected = False
    api = MagicMock(spec=ZentralySwitchApi)
    entity = ZentralySwitch(
        device=platform_device, switch_api=api, capability=SwitchCapability.POWER
    )
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()
    api.async_set_power.assert_not_awaited()


async def test_missing_power_is_unknown(platform_device: MagicMock) -> None:
    """An unknown power value does not retain an old on state."""
    api = MagicMock(spec=ZentralySwitchApi)
    api.async_get_power.side_effect = [True, None]
    entity = ZentralySwitch(
        device=platform_device, switch_api=api, capability=SwitchCapability.POWER
    )
    await entity.async_update()
    assert entity.is_on is True
    await entity.async_update()
    assert entity.is_on is None
    assert entity.available
