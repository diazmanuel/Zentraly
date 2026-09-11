"""Tests for kinetic devices through Home Assistant's entity platforms."""

from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest

from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.button import _create_button_entities
from homeassistant.components.zentraly.const import DOMAIN
from homeassistant.components.zentraly.models import ZentralyConfigEntry
from homeassistant.components.zentraly.number import _create_number_entities
from homeassistant.components.zentraly.select import _create_select_entities
from homeassistant.components.zentraly.sensor import _create_sensor_entities
from homeassistant.components.zentraly.switch import _create_switch_entities
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from tests.common import MockConfigEntry, async_fire_time_changed

MAC = "aabbccddeeff"


@pytest.fixture
async def kinetic_entry(
    hass: HomeAssistant,
) -> AsyncIterator[tuple[ZentralyConfigEntry, list[dict[str, Any]]]]:
    """Set up every real platform on a dual switch with a controlled connection."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="ZTIKD0100000001",
        data={
            CONF_DEVICE_ID: "ZTIKD0100000001",
            CONF_HOST: "192.168.1.42",
            CONF_PORT: 80,
            CONF_MAC: MAC,
            CONF_PASSWORD: "password",
        },
    )
    entry.add_to_hass(hass)
    sent: list[dict[str, Any]] = []

    async def connect(api: ZentralyApi) -> None:
        api._set_connected(True)

    async def execute(
        api: ZentralyApi, builder: Callable[[int], dict[str, Any]]
    ) -> tuple[int, dict[str, Any]]:
        command = builder(len(sent) + 1)
        sent.append(command)
        response = {"cmd": command["cmd"], "rid": command["rid"], "status": 200}
        if command["cmd"] == "readAttr":
            values = {
                (65000, 2): "1.2.3",
                (65000, 3): "2",
                (65534, 100): -55,
                (65006, 0): 0,
                (65006, 28): 2,
                (65006, 29): 0,
                (65006, 50): 0,
                (65006, 51): 120,
            }
            response["attrs"] = [
                {"id": attr["id"], "val": values[(command["cluster"], attr["id"])]}
                for attr in command["attrs"]
            ]
        return command["rid"], response

    with (
        patch.object(ZentralyApi, "async_validate_password", return_value=MAC),
        patch.object(ZentralyApi, "async_connect", connect),
        patch.object(ZentralyApi, "async_execute_command", execute),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        sent.clear()
        runtime = entry.runtime_data
        yield entry, sent
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    assert runtime.api._report_listeners == {}
    assert runtime.api._connection_state_listeners == set()
    assert runtime.device._action_state_listeners == {}


def _entity_id(
    hass: HomeAssistant, platform: str, capability: str, channel: int
) -> str:
    """Look up a channel entity by its stable unique identifier."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"ZTIKD0100000001_{capability}_channel_{channel}"
    )
    assert entity_id is not None
    return entity_id


async def test_entities_and_identity(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Two sets of channel entities share one physical device and connection."""
    entry, sent = kinetic_entry
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert len(entities) == 12
    assert len({entity.unique_id for entity in entities}) == 12
    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert {entity.device_id for entity in entities} == {device.id}
    assert device.identifiers == {(DOMAIN, "ZTIKD0100000001")}
    assert device.model == "ztikd"
    assert entry.runtime_data.children == {}
    assert len(entry.runtime_data.api._report_listeners[MAC]) == 1
    for channel in (1, 2):
        number_id = _entity_id(hass, "number", "timer_off", channel)
        number = entity_registry.async_get(number_id)
        assert number.entity_category is EntityCategory.CONFIG
        state = hass.states.get(number_id)
        assert state.state == "2.0"
        assert state.attributes["min"] == 1
        assert state.attributes["max"] == 30
        assert state.attributes["step"] == 1
        assert state.attributes["unit_of_measurement"] == "min"
        assert state.attributes["friendly_name"].endswith(
            f"Automatic shut-off duration channel {channel}"
        )
        enable = entity_registry.async_get(
            _entity_id(hass, "switch", "timer_off_enable", channel)
        )
        assert enable.entity_category is EntityCategory.CONFIG
    assert sent == []


@pytest.mark.parametrize("channel", [1, 2])
@pytest.mark.parametrize(
    ("service", "command_id", "state"),
    [
        pytest.param("turn_on", 1, "on", id="on"),
        pytest.param("turn_off", 0, "off", id="off"),
    ],
)
async def test_power_updates_only_its_mode(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
    channel: int,
    service: str,
    command_id: int,
    state: str,
) -> None:
    """Power switches its channel to manual without an additional mode write."""
    _, sent = kinetic_entry
    power = _entity_id(hass, "switch", "power", channel)
    mode = _entity_id(hass, "select", "operation_mode", channel)
    other_mode = _entity_id(hass, "select", "operation_mode", 3 - channel)
    assert hass.states.get(mode).state == "auto"
    await hass.services.async_call(
        "switch", service, {"entity_id": power}, blocking=True
    )
    assert hass.states.get(power).state == state
    assert hass.states.get(mode).state == "manual"
    assert hass.states.get(other_mode).state == "auto"
    assert sent == [
        {
            "cmd": "zclCmd",
            "rid": 1,
            "mac": MAC,
            "ep": channel,
            "cluster": 65006,
            "cmdId": command_id,
        }
    ]


@pytest.mark.parametrize("channel", [1, 2])
@pytest.mark.parametrize(
    ("platform", "capability", "service", "data", "attribute", "value"),
    [
        pytest.param(
            "number",
            "timer_off",
            "set_value",
            {"value": 1},
            51,
            60,
            id="minimum-duration",
        ),
        pytest.param(
            "number",
            "timer_off",
            "set_value",
            {"value": 30},
            51,
            1800,
            id="maximum-duration",
        ),
        pytest.param("switch", "timer_off_enable", "turn_on", {}, 50, 1, id="enable"),
        pytest.param("switch", "timer_off_enable", "turn_off", {}, 50, 0, id="disable"),
        pytest.param("switch", "return_to_crono", "turn_on", {}, 29, 1, id="return-on"),
        pytest.param(
            "switch", "return_to_crono", "turn_off", {}, 29, 0, id="return-off"
        ),
        pytest.param(
            "select",
            "operation_mode",
            "select_option",
            {"option": "manual"},
            28,
            1,
            id="manual",
        ),
        pytest.param(
            "select",
            "operation_mode",
            "select_option",
            {"option": "auto"},
            28,
            2,
            id="automatic",
        ),
    ],
)
async def test_setting_writes_only_its_attribute(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
    channel: int,
    platform: str,
    capability: str,
    service: str,
    data: dict[str, str | int],
    attribute: int,
    value: int,
) -> None:
    """Configuration changes do not run the ZTEIM timer sequence."""
    _, sent = kinetic_entry
    entity_id = _entity_id(hass, platform, capability, channel)
    await hass.services.async_call(
        platform, service, {"entity_id": entity_id, **data}, blocking=True
    )
    assert sent == [
        {
            "cmd": "writeAttr",
            "rid": 1,
            "mac": MAC,
            "ep": channel,
            "cluster": 65006,
            "attrs": [{"id": attribute, "type": 41, "val": value}],
        }
    ]
    assert hass.states.get(_entity_id(hass, "switch", "power", channel)).state == "off"


@pytest.mark.parametrize("value", [0, 31])
async def test_reject_invalid_duration_service(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
    value: int,
) -> None:
    """Invalid number actions never reach the transport."""
    _, sent = kinetic_entry
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": _entity_id(hass, "number", "timer_off", 1), "value": value},
            blocking=True,
        )
    assert sent == []


async def test_partial_reports_and_channel_recovery(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
) -> None:
    """Endpoint two can restore availability without corrupting other states."""
    entry, sent = kinetic_entry
    api = entry.runtime_data.api
    device = entry.runtime_data.device
    with patch.object(api, "async_execute_command", return_value=None):
        await device.async_execute_command(lambda rid: {})
    assert not device.available
    api._handle_report(
        {
            "cmd": "report",
            "data": [
                {"mac": MAC, "ep": 2, "cluster": 65006, "id": 51, "val": 239},
                {"mac": MAC, "ep": 2, "cluster": 65006, "id": 50, "val": 1},
                {"mac": MAC, "ep": 2, "cluster": 65006, "id": 0, "val": 100},
                {"mac": MAC, "ep": 1, "cluster": 65006, "id": 0, "val": 101},
                {"mac": MAC, "ep": 1, "cluster": 65006, "id": 51, "val": 0},
                {"mac": "other", "ep": 1, "cluster": 65006, "id": 50, "val": 1},
                {"mac": MAC, "ep": 3, "cluster": 65006, "id": 28, "val": 1},
                {"mac": MAC, "ep": 2, "cluster": 65006, "id": 29},
            ],
        }
    )
    assert device.available
    assert hass.states.get(_entity_id(hass, "number", "timer_off", 2)).state == "3.0"
    assert (
        hass.states.get(_entity_id(hass, "switch", "timer_off_enable", 2)).state == "on"
    )
    assert hass.states.get(_entity_id(hass, "switch", "power", 2)).state == "on"
    assert hass.states.get(_entity_id(hass, "number", "timer_off", 1)).state == "2.0"
    assert hass.states.get(_entity_id(hass, "switch", "power", 1)).state == "off"
    assert (
        hass.states.get(_entity_id(hass, "switch", "timer_off_enable", 1)).state
        == "off"
    )
    assert (
        hass.states.get(_entity_id(hass, "select", "operation_mode", 2)).state == "auto"
    )
    assert sent == []


async def test_reconnect_only_reads_configuration(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
) -> None:
    """Power restoration never restarts a timer or writes control values."""
    entry, sent = kinetic_entry
    api = entry.runtime_data.api
    api._set_connected(False)
    assert (
        hass.states.get(_entity_id(hass, "number", "timer_off", 1)).state
        == "unavailable"
    )
    api._set_connected(True)
    await hass.async_block_till_done()
    assert sent
    assert {command["cmd"] for command in sent} == {"readAttr"}
    sent.clear()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert sent
    assert {command["cmd"] for command in sent} == {"readAttr"}
    assert hass.states.get(_entity_id(hass, "number", "timer_off", 1)).state == "2.0"


def test_single_channel_entity_ids() -> None:
    """Single channel models keep capability IDs without a channel suffix."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTIKS0100000001")
    device = create_device(api, "ZTIKS0100000001", MAC)
    entities = (
        _create_button_entities(device)
        + _create_number_entities(device)
        + _create_select_entities(device)
        + _create_sensor_entities(device)
        + _create_switch_entities(device)
    )
    assert {entity.unique_id for entity in entities} == {
        "ZTIKS0100000001_reset_device",
        "ZTIKS0100000001_wifi_signal_power",
        "ZTIKS0100000001_power",
        "ZTIKS0100000001_return_to_crono",
        "ZTIKS0100000001_timer_off_enable",
        "ZTIKS0100000001_timer_off",
        "ZTIKS0100000001_operation_mode",
    }
    assert all(entity.device_info == device.device_info for entity in entities)


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(None, id="timeout"),
        pytest.param((7, {"cmd": "zclCmd", "rid": 7, "status": 400}), id="rejected"),
        pytest.param((7, {"cmd": "zclCmd", "rid": 8, "status": 200}), id="wrong-rid"),
        pytest.param(
            (7, {"cmd": "writeAttr", "rid": 7, "status": 200}), id="wrong-command"
        ),
    ],
)
async def test_failed_power_does_not_change_mode(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
    response: tuple[int, dict[str, Any]] | None,
) -> None:
    """Only a confirmed power command publishes the manual-mode effect."""
    entry, _ = kinetic_entry
    mode = _entity_id(hass, "select", "operation_mode", 1)
    with (
        patch.object(
            entry.runtime_data.api, "async_execute_command", return_value=response
        ),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": _entity_id(hass, "switch", "power", 1)},
            blocking=True,
        )
    entry.runtime_data.api._handle_report(
        {
            "cmd": "report",
            "data": [
                {"mac": MAC, "ep": 1, "cluster": 65006, "id": 0, "val": 0},
            ],
        }
    )
    assert hass.states.get(mode).state == "auto"
    assert hass.states.get(_entity_id(hass, "switch", "power", 1)).state == "off"


async def test_configuration_reports_and_reset(
    hass: HomeAssistant,
    kinetic_entry: tuple[ZentralyConfigEntry, list[dict[str, Any]]],
    entity_registry: er.EntityRegistry,
) -> None:
    """Reports update readable settings even if the spreadsheet marks them nonreportable."""
    entry, sent = kinetic_entry
    entry.runtime_data.api._handle_report(
        {
            "cmd": "report",
            "data": [
                {"mac": MAC, "ep": 2, "cluster": 65006, "id": 28, "val": 1},
                {"mac": MAC, "ep": 2, "cluster": 65006, "id": 29, "val": 1},
                {"mac": MAC, "ep": 1, "cluster": 65534, "id": 100, "val": -60},
            ],
        }
    )
    assert (
        hass.states.get(_entity_id(hass, "select", "operation_mode", 2)).state
        == "manual"
    )
    assert (
        hass.states.get(_entity_id(hass, "select", "operation_mode", 1)).state == "auto"
    )
    assert (
        hass.states.get(_entity_id(hass, "switch", "return_to_crono", 2)).state == "on"
    )
    assert (
        hass.states.get(_entity_id(hass, "switch", "return_to_crono", 1)).state == "off"
    )
    wifi = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, "ZTIKD0100000001_wifi_signal_power"
    )
    assert hass.states.get(wifi).state == "-60"
    reset = entity_registry.async_get_entity_id(
        "button", DOMAIN, "ZTIKD0100000001_reset_device"
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": reset}, blocking=True
    )
    assert sent == [
        {
            "cmd": "writeAttr",
            "rid": 1,
            "mac": MAC,
            "ep": 1,
            "cluster": 65000,
            "attrs": [{"id": 12, "type": 41, "val": 1}],
        }
    ]
