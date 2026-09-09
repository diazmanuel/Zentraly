"""Tests for Zentraly sensor values and units."""

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.zentraly.device_classes.sensor.api import (
    ZentralySensorApi,
)
from homeassistant.components.zentraly.device_classes.sensor.capabilities import (
    SensorCapability,
)
from homeassistant.components.zentraly.sensor import ZentralySensor
from homeassistant.const import UnitOfVolumeFlowRate


async def test_flow_rate(platform_device: MagicMock) -> None:
    """Expose the measured flow using Home Assistant's standard unit."""
    api = MagicMock(spec=ZentralySensorApi)
    api.async_get_dhw_flow_rate.return_value = 7.5
    entity = ZentralySensor(
        device=platform_device,
        sensor_api=api,
        capability=SensorCapability.DHW_FLOW_RATE,
    )

    await entity.async_update()

    assert entity.native_value == 7.5
    assert entity.native_unit_of_measurement == UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    assert entity.unique_id == "ZTTIN0100000631_dhw_flow_rate"
    api.async_get_dhw_flow_rate.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("connected", "opentherm"),
    [
        pytest.param(False, True, id="gateway-disconnected"),
        pytest.param(True, False, id="opentherm-disconnected"),
    ],
)
async def test_flow_unavailable(
    platform_device: MagicMock, connected: bool, opentherm: bool
) -> None:
    """Do not request flow when its connection is unavailable."""
    platform_device.connected = connected
    platform_device.opentherm_connected = opentherm
    api = MagicMock(spec=ZentralySensorApi)
    entity = ZentralySensor(
        device=platform_device,
        sensor_api=api,
        capability=SensorCapability.DHW_FLOW_RATE,
    )
    await entity.async_update()
    assert entity.native_value is None
    api.async_get_dhw_flow_rate.assert_not_awaited()


def test_flow_report(platform_device: MagicMock) -> None:
    """Accept a numeric report and preserve it after malformed input."""
    api = MagicMock(spec=ZentralySensorApi)
    entity = ZentralySensor(
        device=platform_device,
        sensor_api=api,
        capability=SensorCapability.DHW_FLOW_RATE,
    )
    with patch.object(entity, "async_write_ha_state") as publish:
        entity._handle_state_update({SensorCapability.DHW_FLOW_RATE: 8.0})
        entity._handle_state_update({SensorCapability.DHW_FLOW_RATE: "invalid"})
    assert entity.native_value == 8.0
    publish.assert_called_once_with()
