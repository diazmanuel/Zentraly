"""Tests for model-owned climate configuration and validation."""

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from zentraly import ClimateConfiguration, ClimateOperationMode, ZentralyApi
from zentraly.devices.zttin import ZttinCommands

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.climate import ZentralyClimate


@pytest.mark.parametrize(
    "model",
    [
        pytest.param("ZTTIN", id="zttin"),
        pytest.param("ZTTWZ", id="zttwz"),
        pytest.param("ZTREA", id="ztrea"),
    ],
)
def test_existing_climate_configuration(model: str) -> None:
    """Existing models expose the same range, step, modes, and features."""
    api = MagicMock(spec=ZentralyApi)
    device = create_device(api, f"{model}0100000001", "aa")
    entity = ZentralyClimate(device)
    assert entity.min_temp == 5
    assert entity.max_temp == 30
    assert entity.target_temperature_step == 0.5
    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    assert entity.preset_modes == [PRESET_NONE, PRESET_AWAY]
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert entity.supported_features & ClimateEntityFeature.PRESET_MODE


class RestrictedClimateCommands(ZttinCommands):
    """Test model configured without changes to the API or entity."""

    climate_configuration = ClimateConfiguration(
        minimum_temperature=10,
        maximum_temperature=25,
        temperature_step=1,
        operation_modes=(ClimateOperationMode.OFF, ClimateOperationMode.MANUAL),
    )


def test_model_configuration_controls_ui_and_commands() -> None:
    """One declaration changes the UI limits and protocol validation together."""
    device = create_device(MagicMock(spec=ZentralyApi), "ZTTIN0100000001", "aa")
    commands = RestrictedClimateCommands()
    device.commands = commands
    entity = ZentralyClimate(device)
    assert entity.min_temp == 10
    assert entity.max_temp == 25
    assert entity.target_temperature_step == 1
    assert entity.hvac_modes == [HVACMode.OFF, HVACMode.HEAT]
    assert entity.preset_modes is None
    assert not entity.supported_features & ClimateEntityFeature.PRESET_MODE
    assert (
        commands.build_write_target_temperature(1, "aa", 16)["attrs"][0]["val"] == 1600
    )
    with pytest.raises(ValueError):
        commands.build_write_target_temperature(1, "aa", 5)
    with pytest.raises(ValueError):
        commands.build_write_target_temperature(1, "aa", 20.5)
    with pytest.raises(ValueError):
        commands.build_write_operation_mode(1, "aa", ClimateOperationMode.AUTO)
    with pytest.raises(ValueError):
        commands.build_write_operation_mode(1, "aa", ClimateOperationMode.AWAY)


@pytest.mark.parametrize(
    ("mode_after", "expected"),
    [
        pytest.param(None, HVACMode.AUTO, id="preserve-mode"),
        pytest.param(
            ClimateOperationMode.MANUAL, HVACMode.HEAT, id="manual-after-write"
        ),
    ],
)
async def test_mode_after_setpoint(
    mode_after: ClimateOperationMode | None, expected: HVACMode
) -> None:
    """Only models declaring a mode transition update the displayed mode."""
    device = create_device(MagicMock(spec=ZentralyApi), "ZTTIN0100000001", "aa")
    with patch.object(
        device.commands,
        "climate_configuration",
        replace(ZttinCommands.climate_configuration, mode_after_setpoint=mode_after),
    ):
        entity = ZentralyClimate(device)
        entity._apply_operation_mode(ClimateOperationMode.AUTO)
        with (
            patch.object(
                entity._climate_api, "async_set_target_temperature", return_value=True
            ),
            patch.object(entity, "async_write_ha_state"),
        ):
            await entity.async_set_temperature(temperature=22)
    assert entity.hvac_mode is expected
