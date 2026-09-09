"""Tests for Zentraly thermostat modes and setpoints."""

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.climate import PRESET_AWAY, HVACAction, HVACMode
from homeassistant.components.zentraly.climate import ZentralyClimate
from homeassistant.components.zentraly.device_classes.climate.api import (
    ZentralyClimateApi,
)
from homeassistant.components.zentraly.device_classes.climate.capabilities import (
    ClimateCapability,
)
from homeassistant.components.zentraly.device_classes.types import ClimateOperationMode


@pytest.mark.parametrize(
    ("mode", "operation"),
    [
        pytest.param(HVACMode.OFF, ClimateOperationMode.OFF, id="off"),
        pytest.param(HVACMode.HEAT, ClimateOperationMode.MANUAL, id="heat"),
        pytest.param(HVACMode.AUTO, ClimateOperationMode.AUTO, id="auto"),
    ],
)
async def test_hvac_mode(
    platform_device: MagicMock, mode: HVACMode, operation: ClimateOperationMode
) -> None:
    """Translate Home Assistant modes into device operations."""
    api = MagicMock(spec=ZentralyClimateApi)
    api.supports.return_value = True
    api.async_set_operation_mode.return_value = True
    entity = ZentralyClimate(platform_device, climate_api=api)
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_hvac_mode(mode)
    assert entity.hvac_mode == mode
    api.async_set_operation_mode.assert_awaited_once_with(operation)


@pytest.mark.parametrize(
    ("success", "expected"),
    [
        pytest.param(True, 22.0, id="success"),
        pytest.param(False, 20.0, id="failure"),
    ],
)
async def test_temperature_write(
    platform_device: MagicMock, success: bool, expected: float
) -> None:
    """A failed setpoint write preserves the last reported temperature."""
    api = MagicMock(spec=ZentralyClimateApi)
    api.supports.return_value = True
    api.async_set_target_temperature.return_value = success
    entity = ZentralyClimate(platform_device, climate_api=api)
    with patch.object(entity, "async_write_ha_state"):
        entity._handle_state_update({ClimateCapability.TARGET_TEMPERATURE: 20.0})
        await entity.async_set_temperature(temperature=22.0)
    assert entity.target_temperature == expected
    api.async_set_target_temperature.assert_awaited_once_with(22.0)


def test_away_report(platform_device: MagicMock) -> None:
    """Away mode displays its setpoint and preserves the reported heat demand."""
    api = MagicMock(spec=ZentralyClimateApi)
    api.supports.return_value = True
    entity = ZentralyClimate(platform_device, climate_api=api)
    with patch.object(entity, "async_write_ha_state"):
        entity._handle_state_update(
            {
                ClimateCapability.LOCAL_TEMPERATURE: 19.0,
                ClimateCapability.TARGET_TEMPERATURE: 22.0,
                ClimateCapability.AWAY_TEMPERATURE: 15.0,
                ClimateCapability.OPERATION_MODE: ClimateOperationMode.AWAY,
                ClimateCapability.HEAT_DEMAND: True,
            }
        )
    assert entity.current_temperature == 19.0
    assert entity.target_temperature == 15.0
    assert entity.preset_mode == PRESET_AWAY
    assert entity.hvac_action == HVACAction.HEATING
