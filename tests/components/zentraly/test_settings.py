"""Tests for reusable configuration controls and their wire conversions."""

from collections.abc import AsyncIterator, Callable
import logging
from typing import Any
from unittest.mock import patch

import pytest
from zentraly import (
    NumberCapability,
    SwitchCapability,
    ZentralyApi,
    ZentralyApiError,
    ZentralySwitchApi,
)

from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.number import (
    ZentralyNumber,
    _create_number_entities,
)
from homeassistant.components.zentraly.select import (
    ZentralySelect,
    _create_select_entities,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_component import EntityComponent


@pytest.mark.parametrize(
    (
        "capability",
        "attribute",
        "raw",
        "value",
        "limits",
        "unit",
        "invalid",
        "report_raw",
        "report_value",
    ),
    [
        pytest.param(
            NumberCapability.AWAY_TEMPERATURE,
            17,
            1700,
            17.0,
            (5, 30, 1),
            "°C",
            17.5,
            1800,
            18.0,
            id="away-temperature",
        ),
        pytest.param(
            NumberCapability.TEMPERATURE_OFFSET,
            16,
            -120,
            -1.2,
            (-6, 6, 0.1),
            "°C",
            6.1,
            -110,
            -1.1,
            id="temperature-correction",
        ),
        pytest.param(
            NumberCapability.DISPLAY_BRIGHTNESS,
            100,
            0,
            0.0,
            (0, 100, 1),
            "%",
            101,
            20,
            20.0,
            id="display-brightness",
        ),
    ],
)
@pytest.mark.parametrize("model", ["ZTTWZ", "ZTTIN"])
async def test_number_setting_roundtrip(
    hass: HomeAssistant,
    model: str,
    capability: NumberCapability,
    attribute: int,
    raw: int,
    value: float,
    limits: tuple[float, float, float],
    unit: str,
    invalid: float,
    report_raw: int,
    report_value: float,
) -> None:
    """Read, write and report a setting without defaults or extra mode writes."""
    api = ZentralyApi("192.168.1.42", 80, "password", f"{model}0100000001")
    api._set_connected(True)
    device = create_device(api, api.device_id, "aa")
    device.set_switch_state(SwitchCapability.ALWAYS_ON_DISPLAY, True)
    entity = next(
        e
        for e in _create_number_entities(device)
        if e.translation_key == capability.value
    )
    entity.entity_id = "number.zentraly_setting"
    component = EntityComponent(logging.getLogger(__name__), "number", hass)
    sent: list[dict[str, Any]] = []

    async def execute(
        builder: Callable[[int], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        command = builder(1)
        sent.append(command)
        return 1, {**command, "status": 200, "attrs": [{"id": attribute, "val": raw}]}

    with patch.object(api, "async_execute_command", side_effect=execute):
        with patch(
            "homeassistant.helpers.entity.Entity.async_schedule_update_ha_state"
        ):
            await component.async_add_entities([entity])
        assert entity.native_value is None
        assert entity.entity_category is EntityCategory.CONFIG
        assert (
            entity.native_min_value,
            entity.native_max_value,
            entity.native_step,
        ) == limits
        assert entity.native_unit_of_measurement == unit
        await entity.async_update()
        assert entity.native_value == value
        assert sent == [
            {
                "cmd": "readAttr",
                "rid": 1,
                "mac": "aa",
                "cluster": 65513,
                "ep": 1,
                "attrs": [{"id": attribute, "type": 41}],
            }
        ]
        sent.clear()
        await entity.async_set_native_value(value)
        assert sent == [
            {
                "cmd": "writeAttr",
                "rid": 1,
                "mac": "aa",
                "cluster": 65513,
                "ep": 1,
                "attrs": [{"id": attribute, "type": 41, "val": raw}],
            }
        ]
        sent.clear()
        with pytest.raises(ServiceValidationError):
            await entity.async_set_native_value(invalid)
        assert sent == []
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {
                        "mac": "aa",
                        "ep": 1,
                        "cluster": 65513,
                        "id": attribute,
                        "val": report_raw,
                    }
                ],
            }
        )
        assert entity.native_value == report_value
        assert sent == []
        await entity.async_remove()
    assert api._report_listeners == {}


@pytest.mark.parametrize(("option", "raw"), [("temperature", 1), ("time", 0)])
@pytest.mark.parametrize("model", ["ZTTWZ", "ZTTIN"])
async def test_display_setting_roundtrip(
    model: str, hass: HomeAssistant, option: str, raw: int
) -> None:
    """Display configuration uses its own enum and never writes operation mode."""
    api = ZentralyApi("192.168.1.42", 80, "password", f"{model}0100000001")
    api._set_connected(True)
    device = create_device(api, api.device_id, "aa")
    device.set_switch_state(SwitchCapability.ALWAYS_ON_DISPLAY, True)
    entity = _create_select_entities(device)[0]
    entity.entity_id = "select.zentraly_display"
    component = EntityComponent(logging.getLogger(__name__), "select", hass)
    sent: list[dict[str, Any]] = []

    async def execute(
        builder: Callable[[int], dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        command = builder(1)
        sent.append(command)
        return 1, {**command, "status": 200, "attrs": [{"id": 102, "val": raw}]}

    with patch.object(api, "async_execute_command", side_effect=execute):
        with patch(
            "homeassistant.helpers.entity.Entity.async_schedule_update_ha_state"
        ):
            await component.async_add_entities([entity])
        assert entity.current_option is None
        assert entity.options == ["temperature", "time"]
        assert entity.entity_category is EntityCategory.CONFIG
        await entity.async_update()
        assert entity.current_option == option
        sent.clear()
        await entity.async_select_option(option)
        assert sent == [
            {
                "cmd": "writeAttr",
                "rid": 1,
                "mac": "aa",
                "cluster": 65513,
                "ep": 1,
                "attrs": [{"id": 102, "type": 41, "val": raw}],
            }
        ]
        sent.clear()
        with pytest.raises(ServiceValidationError):
            await entity.async_select_option("manual")
        assert sent == []
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "aa", "ep": 1, "cluster": 65513, "id": 102, "val": 1 - raw}
                ],
            }
        )
        assert entity.current_option == entity.options[raw]
        api._handle_report(
            {
                "cmd": "report",
                "data": [{"mac": "aa", "ep": 1, "cluster": 65513, "id": 102, "val": 2}],
            }
        )
        assert entity.current_option == entity.options[raw]
        await entity.async_remove()
    assert api._report_listeners == {}


@pytest.fixture(params=["ZTTWZ", "ZTTIN"])
async def display_controls(
    request: pytest.FixtureRequest,
    hass: HomeAssistant,
) -> AsyncIterator[tuple[ZentralyApi, ZentralyNumber, ZentralySelect]]:
    """Load dependent controls with no assumed enabling-switch state."""
    api = ZentralyApi("192.168.1.42", 80, "password", f"{request.param}0100000001")
    api._set_connected(True)
    device = create_device(api, api.device_id, "aa")
    numbers = {e.translation_key: e for e in _create_number_entities(device)}
    brightness = numbers["display_brightness"]
    away = numbers["away_temperature"]
    display = _create_select_entities(device)[0]
    brightness.entity_id = "number.display_brightness"
    display.entity_id = "select.display_mode"
    number_component = EntityComponent(logging.getLogger(__name__), "number", hass)
    select_component = EntityComponent(logging.getLogger(__name__), "select", hass)
    with patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state"):
        await number_component.async_add_entities([brightness])
    with patch("homeassistant.helpers.entity.Entity.async_schedule_update_ha_state"):
        await select_component.async_add_entities([display])
    assert not brightness.available
    assert not display.available
    assert away.available
    yield api, brightness, display
    await brightness.async_remove()
    await display.async_remove()
    assert api._report_listeners == {}


async def test_display_dependency_report(
    hass: HomeAssistant,
    display_controls: tuple[ZentralyApi, ZentralyNumber, ZentralySelect],
) -> None:
    """A report enables controls before applying their values, then disables them."""
    api, brightness, display = display_controls
    api._handle_report(
        {
            "cmd": "report",
            "data": [
                {"mac": "aa", "ep": 1, "cluster": 65513, "id": 100, "val": 30},
                {"mac": "aa", "ep": 1, "cluster": 65513, "id": 102, "val": 1},
                {"mac": "aa", "ep": 1, "cluster": 65513, "id": 101, "val": 1},
            ],
        }
    )
    assert brightness.available
    assert display.available
    assert hass.states.get(brightness.entity_id).state == "30.0"
    assert hass.states.get(display.entity_id).state == "temperature"
    api._handle_report(
        {
            "cmd": "report",
            "data": [
                {"mac": "aa", "ep": 1, "cluster": 65513, "id": 101, "val": 0},
            ],
        }
    )
    assert not brightness.available
    assert not display.available
    assert hass.states.get(brightness.entity_id).state == "unavailable"
    assert hass.states.get(display.entity_id).state == "unavailable"
    assert brightness.native_value == 30.0
    assert display.current_option == "temperature"


async def test_display_dependency_poll_and_write(
    display_controls: tuple[ZentralyApi, ZentralyNumber, ZentralySelect],
) -> None:
    """Reads and successful writes publish switch state; rejected writes do not."""
    api, brightness, display = display_controls
    switches = ZentralySwitchApi(brightness._device)
    with patch.object(
        api,
        "async_execute_command",
        return_value=(
            1,
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": 101, "val": 1}],
            },
        ),
    ):
        assert await switches.async_get_always_on_display() is True
    assert brightness.available
    assert display.available
    with patch.object(
        api,
        "async_execute_command",
        return_value=(
            1,
            {
                "cmd": "writeAttr",
                "rid": 1,
                "status": 200,
            },
        ),
    ):
        assert await switches.async_set_always_on_display(False)
        assert not brightness.available
        assert not display.available
        assert await switches.async_set_always_on_display(True)
        assert brightness.available
        assert display.available
    with (
        patch.object(
            api,
            "async_execute_command",
            return_value=(
                1,
                {
                    "cmd": "writeAttr",
                    "rid": 1,
                    "status": 500,
                },
            ),
        ),
        pytest.raises(ZentralyApiError),
    ):
        await switches.async_set_always_on_display(False)
    assert brightness.available
    assert display.available
