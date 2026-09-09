"""Tests for Zentraly reset actions."""

from unittest.mock import MagicMock

import pytest

from homeassistant.components.zentraly.button import ZentralyButton
from homeassistant.components.zentraly.device_classes.button.api import (
    ZentralyButtonApi,
)
from homeassistant.components.zentraly.device_classes.button.capabilities import (
    ButtonCapability,
)


@pytest.mark.parametrize(
    ("capability", "method"),
    [
        pytest.param(ButtonCapability.RESET_DEVICE, "async_reset_device", id="device"),
        pytest.param(ButtonCapability.RESET_BOILER, "async_reset_boiler", id="boiler"),
    ],
)
async def test_press(
    platform_device: MagicMock, capability: ButtonCapability, method: str
) -> None:
    """Route each reset button to its own command."""
    api = MagicMock(spec=ZentralyButtonApi)
    entity = ZentralyButton(
        device=platform_device, button_api=api, capability=capability
    )
    await entity.async_press()
    getattr(api, method).assert_awaited_once_with()
    assert entity.available


@pytest.mark.parametrize(
    ("connected", "opentherm"),
    [
        pytest.param(False, True, id="gateway-disconnected"),
        pytest.param(True, False, id="opentherm-disconnected"),
    ],
)
async def test_unavailable_boiler(
    platform_device: MagicMock, connected: bool, opentherm: bool
) -> None:
    """Do not send a boiler reset when the connection is unavailable."""
    platform_device.connected = connected
    platform_device.opentherm_connected = opentherm
    api = MagicMock(spec=ZentralyButtonApi)
    entity = ZentralyButton(
        device=platform_device, button_api=api, capability=ButtonCapability.RESET_BOILER
    )
    await entity.async_press()
    assert not entity.available
    api.async_reset_boiler.assert_not_awaited()
