"""Tests for Zentraly sensor values and units."""

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.device_classes.sensor.api import (
    ZentralySensorApi,
)
from homeassistant.components.zentraly.device_classes.sensor.capabilities import (
    SensorCapability,
)
from homeassistant.components.zentraly.device_classes.types import ZentralyOutputType
from homeassistant.components.zentraly.sensor import ZentralySensor
from homeassistant.const import UnitOfVolumeFlowRate


@pytest.mark.parametrize("model", ["ZTBIN", "ZTTWZ"])
@pytest.mark.parametrize(
    ("capability", "attribute_id", "expected"),
    [
        pytest.param(SensorCapability.CH_SETPOINT, 1, 20.5, id="ch-setpoint"),
        pytest.param(SensorCapability.DHW_SETPOINT, 56, 20.5, id="dhw-setpoint"),
        pytest.param(SensorCapability.MODULATION_LEVEL, 17, 2050, id="modulation"),
        pytest.param(SensorCapability.CH_WATER_PRESSURE, 18, 2050, id="pressure"),
        pytest.param(SensorCapability.DHW_FLOW_RATE, 19, 2050, id="flow"),
        pytest.param(SensorCapability.FEED_TEMPERATURE, 25, 2050, id="feed"),
        pytest.param(SensorCapability.DHW_TEMPERATURE, 26, 2050, id="dhw"),
    ],
)
async def test_opentherm_measurement_scale(
    model: str,
    capability: SensorCapability,
    attribute_id: int,
    expected: float,
) -> None:
    """Convert setpoints to Celsius while preserving unscaled measurements."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTTWZ0100000001")
    api._set_connected(True)
    device = create_device(api, f"{model}0100000001", "bb")
    device.set_output_type(ZentralyOutputType.OPENTHERM)
    entity = ZentralySensor(
        device=device,
        sensor_api=ZentralySensorApi(device),
        capability=capability,
    )

    with patch.object(
        api,
        "async_execute_command",
        return_value=(
            1,
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": attribute_id, "val": 2050}],
            },
        ),
    ):
        await entity.async_update()

    assert entity.native_value == expected


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


async def test_opentherm_loss_clears_flow(platform_device: MagicMock) -> None:
    """An output change immediately clears the previous OpenTherm reading."""
    api = MagicMock(spec=ZentralySensorApi)
    api.async_get_dhw_flow_rate.return_value = 7.5
    entity = ZentralySensor(
        device=platform_device,
        sensor_api=api,
        capability=SensorCapability.DHW_FLOW_RATE,
    )
    await entity.async_update()
    assert entity.native_value == 7.5
    platform_device.opentherm_connected = False
    with patch.object(entity, "async_write_ha_state") as publish:
        entity._handle_device_state()
    assert entity.native_value is None
    assert entity.available
    publish.assert_called_once_with()


async def test_output_poll_recovers_unavailable_device() -> None:
    """Polling continues after a device timeout so it can recover without reports."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTTWZ0100000001")
    api._set_connected(True)
    device = create_device(api, "ZTBIN0100000001", "bb")
    entity = ZentralySensor(
        device=device,
        sensor_api=ZentralySensorApi(device),
        capability=SensorCapability.OUTPUT_TYPE,
    )
    with patch.object(api, "async_execute_command", return_value=None):
        await entity.async_update()
    assert not entity.available
    with patch.object(
        api,
        "async_execute_command",
        return_value=(
            1,
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": 1000, "val": 1}],
            },
        ),
    ):
        await entity.async_update()
    assert entity.available
    assert entity.native_value == "opentherm"
    with patch.object(
        api,
        "async_execute_command",
        return_value=(2, {"cmd": "readAttr", "rid": 2, "status": 200, "attrs": []}),
    ):
        await entity.async_update()
    assert entity.available
    assert entity.native_value is None
    assert device.output_type is ZentralyOutputType.OPENTHERM
