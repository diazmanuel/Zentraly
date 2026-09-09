"""Tests for Zentraly binary sensor states."""

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.zentraly.binary_sensor import ZentralyBinarySensor
from homeassistant.components.zentraly.device_classes.binary_sensor.api import (
    ZentralyBinarySensorApi,
)
from homeassistant.components.zentraly.device_classes.binary_sensor.capabilities import (
    BinarySensorCapability,
)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(True, id="on"),
        pytest.param(False, id="off"),
        pytest.param(None, id="unknown"),
    ],
)
async def test_boiler_state(platform_device: MagicMock, value: bool | None) -> None:
    """Expose the boiler state returned by the device."""
    api = MagicMock(spec=ZentralyBinarySensorApi)
    api.async_get_boiler_on.return_value = value
    entity = ZentralyBinarySensor(
        device=platform_device,
        binary_sensor_api=api,
        capability=BinarySensorCapability.BOILER_ON,
    )
    await entity.async_update()
    assert entity.is_on is value
    api.async_get_boiler_on.assert_awaited_once_with()


async def test_disconnected(platform_device: MagicMock) -> None:
    """Do not query an unavailable gateway."""
    platform_device.connected = False
    api = MagicMock(spec=ZentralyBinarySensorApi)
    entity = ZentralyBinarySensor(
        device=platform_device,
        binary_sensor_api=api,
        capability=BinarySensorCapability.BOILER_ON,
    )
    await entity.async_update()
    assert not entity.available
    api.async_get_boiler_on.assert_not_awaited()


def test_report(platform_device: MagicMock) -> None:
    """Reports update the state while malformed values are ignored."""
    api = MagicMock(spec=ZentralyBinarySensorApi)
    entity = ZentralyBinarySensor(
        device=platform_device,
        binary_sensor_api=api,
        capability=BinarySensorCapability.BOILER_ON,
    )
    with patch.object(entity, "async_write_ha_state") as publish:
        entity._handle_state_update({BinarySensorCapability.BOILER_ON: True})
        entity._handle_state_update({BinarySensorCapability.BOILER_ON: "invalid"})
    assert entity.is_on is True
    publish.assert_called_once_with()


async def test_opentherm_loss_clears_state(platform_device: MagicMock) -> None:
    """An output change clears an earlier OpenTherm flag without another read."""
    api = MagicMock(spec=ZentralyBinarySensorApi)
    api.async_get_ot_dhw_enabled.return_value = True
    entity = ZentralyBinarySensor(
        device=platform_device,
        binary_sensor_api=api,
        capability=BinarySensorCapability.OT_DHW_ENABLED,
    )
    await entity.async_update()
    assert entity.is_on is True
    platform_device.opentherm_connected = False
    with patch.object(entity, "async_write_ha_state") as publish:
        entity._handle_device_state()
    assert entity.is_on is None
    assert entity.available
    publish.assert_called_once_with()
