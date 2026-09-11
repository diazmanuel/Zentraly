"""Tests for partial Zentraly reports and shared report dispatch."""

from collections.abc import Callable
import logging
from typing import Any, Self, override
from unittest.mock import patch

import pytest

from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.binary_sensor import (
    _create_binary_sensor_entities,
)
from homeassistant.components.zentraly.climate import ZentralyClimate
from homeassistant.components.zentraly.commands.base import (
    ReportUpdates,
    ZentralyDeviceCommands,
)
from homeassistant.components.zentraly.device_classes.switch.capabilities import (
    SwitchCapability,
)
from homeassistant.components.zentraly.device_classes.types import ZentralyOutputType
from homeassistant.components.zentraly.models import ZentralyDevice
from homeassistant.components.zentraly.number import _create_number_entities
from homeassistant.components.zentraly.select import _create_select_entities
from homeassistant.components.zentraly.sensor import _create_sensor_entities
from homeassistant.components.zentraly.switch import _create_switch_entities
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent


@pytest.mark.parametrize(
    (
        "domain",
        "model",
        "factory",
        "capability",
        "cluster",
        "attribute_id",
        "raw",
        "property_name",
        "expected",
    ),
    [
        pytest.param(
            "switch",
            "ZTTWZ",
            _create_switch_entities,
            "always_on_display",
            65513,
            101,
            1,
            "is_on",
            True,
            id="setting",
        ),
        pytest.param(
            "number",
            "ZTEIM",
            _create_number_entities,
            "high_voltage_limit",
            65006,
            101,
            255,
            "native_value",
            255.0,
            id="limit",
        ),
        pytest.param(
            "sensor",
            "ZTTWZ",
            _create_sensor_entities,
            "ch_setpoint",
            65535,
            1,
            2050,
            "native_value",
            20.5,
            id="measurement",
        ),
        pytest.param(
            "select",
            "ZTEIM",
            _create_select_entities,
            "operation_mode",
            65006,
            28,
            2,
            "current_option",
            "auto",
            id="mode",
        ),
    ],
)
async def test_partial_report_updates_entity(
    hass: HomeAssistant,
    domain: str,
    model: str,
    factory: Callable[[ZentralyDevice], list[Entity]],
    capability: str,
    cluster: int,
    attribute_id: int,
    raw: int,
    property_name: str,
    expected: bool | float | str,
) -> None:
    """Valid fields survive malformed neighbors; unrelated reports preserve state."""
    api = ZentralyApi("192.168.1.42", 80, "password", f"{model}0100000001")
    api._set_connected(True)
    device = create_device(api, api.device_id, "aa")
    device.set_output_type(ZentralyOutputType.OPENTHERM)
    entity = next(e for e in factory(device) if e.translation_key == capability)
    entity.entity_id = f"{domain}.zentraly_report"
    component = EntityComponent(logging.getLogger(__name__), domain, hass)
    report = {"mac": "aa", "ep": 1, "cluster": cluster, "id": attribute_id, "val": raw}
    with patch.object(api, "async_execute_command") as execute:
        await component.async_add_entities([entity])
        api._handle_report(
            {"cmd": "report", "data": [None, report, {**report, "val": "invalid"}]}
        )
        assert getattr(entity, property_name) == expected
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {**report, "mac": "bb", "val": 0},
                    {**report, "ep": 2, "val": 0},
                    {**report, "id": 99999, "val": 0},
                    {"mac": "aa", "ep": 1, "cluster": cluster, "id": attribute_id},
                ],
            }
        )
        assert getattr(entity, property_name) == expected
        execute.assert_not_awaited()
        await entity.async_remove()
    assert api._report_listeners == {}


@pytest.mark.parametrize("model", ["ZTBIN", "ZTTWZ"])
async def test_opentherm_report_updates_three_indicators(
    hass: HomeAssistant, model: str
) -> None:
    """Output type is applied before a status word, regardless of attribute order."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTTWZ0100000001")
    api._set_connected(True)
    device = create_device(api, f"{model}0100000001", "aa")
    device.set_output_type(ZentralyOutputType.ON_OFF)
    entities = [
        e
        for e in _create_binary_sensor_entities(device)
        if e.translation_key.startswith("ot_")
    ]
    component = EntityComponent(logging.getLogger(__name__), "binary_sensor", hass)
    with patch.object(api, "async_execute_command") as execute:
        await component.async_add_entities(entities)
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "aa", "ep": 1, "cluster": 65535, "id": 0, "val": 3},
                    {"mac": "aa", "ep": 1, "cluster": 65535, "id": 1000, "val": 1},
                ],
            }
        )
        assert [e.is_on for e in entities] == [True, True, True]
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "aa", "ep": 1, "cluster": 65535, "id": 0, "val": 32},
                ],
            }
        )
        assert [e.is_on for e in entities] == [False, False, False]
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "aa", "ep": 1, "cluster": 65535, "id": 1000, "val": 0},
                    {"mac": "aa", "ep": 1, "cluster": 65535, "id": 0, "val": 3},
                ],
            }
        )
        assert [e.is_on for e in entities] == [None, None, None]
        execute.assert_not_awaited()
        for entity in entities:
            await entity.async_remove()
    assert api._report_listeners == {}


async def test_timer_report_preserves_pending_selection(hass: HomeAssistant) -> None:
    """Timer reports share read decoding and cannot overwrite a debounced selection."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTEIM0100000001")
    api._set_connected(True)
    device = create_device(api, api.device_id, "aa")
    entity = next(
        e for e in _create_number_entities(device) if e.translation_key == "timer"
    )
    entity.entity_id = "number.zentraly_report_timer"
    component = EntityComponent(logging.getLogger(__name__), "number", hass)
    report = {
        "cmd": "report",
        "data": [{"mac": "aa", "ep": 1, "cluster": 65006, "id": 9, "val": 601}],
    }
    with patch.object(api, "async_execute_command") as execute:
        await component.async_add_entities([entity])
        api._handle_report(report)
        assert entity.native_value == 10.0
        await entity.async_set_native_value(30)
        api._handle_report(report)
        assert entity.native_value == 30
        execute.assert_not_awaited()
        await entity.async_remove()
    assert api._report_listeners == {}


class ChannelReportCommands(ZentralyDeviceCommands):
    """Minimal channel provider to exercise shared routing independently of models."""

    channel_endpoints = (1, 2, 3)
    capabilities = frozenset({SwitchCapability.POWER})

    @override
    def for_endpoint(self, endpoint: int) -> Self:
        return self

    def parse_report_entry(self, entry: dict[str, Any]) -> ReportUpdates:
        """Leave endpoint filtering to the shared platform under test."""
        return {SwitchCapability.POWER: bool(entry["val"])}


async def test_channel_report_dispatch(hass: HomeAssistant) -> None:
    """The shared platform routes a report only to its MAC and endpoint."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTEIM0100000001")
    api._set_connected(True)
    device = create_device(api, api.device_id, "aa")
    device.commands = ChannelReportCommands()
    entities = _create_switch_entities(device)
    component = EntityComponent(logging.getLogger(__name__), "switch", hass)
    await component.async_add_entities(entities)
    api._handle_report(
        {
            "cmd": "report",
            "data": [
                {"mac": "bb", "ep": 1, "cluster": 65006, "id": 0, "val": 1},
                {"mac": "aa", "ep": 3, "cluster": 65006, "id": 0, "val": 1},
            ],
        }
    )
    assert [e.is_on for e in entities] == [None, None, True]
    for entity in entities:
        await entity.async_remove()
    assert api._report_listeners == {}


async def test_climate_away_report(hass: HomeAssistant) -> None:
    """Away setpoints received by report update climate without polling."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTTWZ0100000001")
    api._set_connected(True)
    device = create_device(api, api.device_id, "aa")
    entity = ZentralyClimate(device)
    entity.entity_id = "climate.zentraly_report"
    component = EntityComponent(logging.getLogger(__name__), "climate", hass)
    with patch.object(api, "async_execute_command") as execute:
        await component.async_add_entities([entity])
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "aa", "ep": 1, "cluster": 65513, "id": 28, "val": 3},
                    {"mac": "aa", "ep": 1, "cluster": 65513, "id": 17, "val": 1800},
                ],
            }
        )
        assert entity.target_temperature == 18.0
        assert entity.preset_mode == "away"
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "aa", "ep": 1, "cluster": 65513, "id": 0, "val": 2100},
                ],
            }
        )
        assert entity.current_temperature == 21.0
        assert entity.target_temperature == 18.0
        execute.assert_not_awaited()
        await entity.async_remove()
    assert api._report_listeners == {}
