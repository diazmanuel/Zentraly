"""Tests for model-owned climate configuration and validation."""

from contextlib import AbstractContextManager, nullcontext
from dataclasses import FrozenInstanceError, replace
from math import inf
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.climate import ZentralyClimate
from homeassistant.components.zentraly.device_classes.climate.command_protocols import (
    OperationModeCommands,
    TargetTemperatureCommands,
)
from homeassistant.components.zentraly.device_classes.climate.configuration import (
    ClimateConfiguration,
)
from homeassistant.components.zentraly.device_classes.types import ClimateOperationMode
from homeassistant.components.zentraly.devices.zttin import ZttinCommands


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


@pytest.mark.parametrize(
    "model",
    [
        pytest.param("ZTTIN", id="zttin"),
        pytest.param("ZTTWZ", id="zttwz"),
        pytest.param("ZTREA", id="ztrea"),
    ],
)
@pytest.mark.parametrize(
    ("temperature", "expectation"),
    [
        pytest.param(5.0, nullcontext(), id="minimum"),
        pytest.param(30.0, nullcontext(), id="maximum"),
        pytest.param(20.5, nullcontext(), id="step"),
        pytest.param(5.004, nullcontext(), id="wire-rounding-preserved"),
        pytest.param(4.5, pytest.raises(ValueError), id="below-minimum"),
        pytest.param(30.5, pytest.raises(ValueError), id="above-maximum"),
        pytest.param(20.25, pytest.raises(ValueError), id="invalid-step"),
    ],
)
def test_setpoint_validation(
    model: str, temperature: float, expectation: AbstractContextManager
) -> None:
    """Shared validation preserves accepted values and each model's wire encoding."""
    device = create_device(MagicMock(spec=ZentralyApi), f"{model}0100000001", "aa")
    commands = cast(TargetTemperatureCommands, device.commands)
    with expectation:
        command = commands.build_write_target_temperature(1, device.mac, temperature)
        assert command["attrs"][0]["val"] == round(temperature * 100)


@pytest.mark.parametrize(
    "model",
    [
        pytest.param("ZTTIN", id="zttin"),
        pytest.param("ZTTWZ", id="zttwz"),
        pytest.param("ZTREA", id="ztrea"),
    ],
)
@pytest.mark.parametrize(
    ("mode", "raw"),
    [
        pytest.param(ClimateOperationMode.OFF, 0, id="off"),
        pytest.param(ClimateOperationMode.MANUAL, 1, id="manual"),
        pytest.param(ClimateOperationMode.AUTO, 2, id="auto"),
        pytest.param(ClimateOperationMode.AWAY, 3, id="away"),
    ],
)
def test_mode_encoding(model: str, mode: ClimateOperationMode, raw: int) -> None:
    """Moving metadata does not change protocol mode values."""
    device = create_device(MagicMock(spec=ZentralyApi), f"{model}0100000001", "aa")
    commands = cast(OperationModeCommands, device.commands)
    assert (
        commands.build_write_operation_mode(1, device.mac, mode)["attrs"][0]["val"]
        == raw
    )


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


def test_configuration_is_immutable() -> None:
    """An entity cannot accidentally change shared model settings."""
    with pytest.raises(FrozenInstanceError):
        ZttinCommands.climate_configuration.temperature_step = 1


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"temperature_step": 0}, id="zero-step"),
        pytest.param({"minimum_temperature": 35}, id="inverted-range"),
        pytest.param({"maximum_temperature": inf}, id="infinite-range"),
        pytest.param(
            {"operation_modes": (ClimateOperationMode.OFF,)},
            id="unsupported-setpoint-mode",
        ),
    ],
)
def test_invalid_configuration(changes: dict) -> None:
    """Model declaration mistakes fail before entities are created."""
    with pytest.raises(ValueError):
        replace(ZttinCommands.climate_configuration, **changes)


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
