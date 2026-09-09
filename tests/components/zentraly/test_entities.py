"""Tests for shared availability across Zentraly platforms."""

from collections.abc import Callable
import logging
from unittest.mock import patch

import pytest

from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.binary_sensor import (
    _create_binary_sensor_entities,
)
from homeassistant.components.zentraly.button import _create_button_entities
from homeassistant.components.zentraly.climate import ZentralyClimate
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
    ("domain", "model", "factory"),
    [
        pytest.param("sensor", "ZTBIN", _create_sensor_entities, id="sensor"),
        pytest.param(
            "binary_sensor", "ZTBIN", _create_binary_sensor_entities, id="binary-sensor"
        ),
        pytest.param("switch", "ZTEIM", _create_switch_entities, id="switch"),
        pytest.param("button", "ZTBIN", _create_button_entities, id="button"),
        pytest.param("number", "ZTEIM", _create_number_entities, id="number"),
        pytest.param("select", "ZTEIM", _create_select_entities, id="select"),
        pytest.param(
            "climate", "ZTTIN", lambda device: [ZentralyClimate(device)], id="climate"
        ),
    ],
)
async def test_platform_device_availability(
    hass: HomeAssistant,
    domain: str,
    model: str,
    factory: Callable[[ZentralyDevice], list[Entity]],
) -> None:
    """Every platform publishes a child outage and recovery without gateway loss."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTTWZ0100000001")
    api._set_connected(True)
    device = create_device(api, f"{model}0100000001", "bb")
    device.set_output_type(ZentralyOutputType.OPENTHERM)
    entity = factory(device)[0]
    entity.hass = hass
    entity.entity_id = f"{domain}.zentraly_test"
    component = EntityComponent(logging.getLogger(__name__), domain, hass)
    with patch.object(entity, "async_write_ha_state") as publish:
        await component.async_add_entities([entity])
        publish.reset_mock()
        assert entity.available
        with patch.object(api, "async_execute_command", return_value=None):
            await device.async_execute_command(lambda rid: {})
        assert not entity.available
        assert device.connected
        publish.assert_called_once_with()
        with patch.object(
            api, "async_execute_command", return_value=(1, {"status": 200})
        ):
            await device.async_execute_command(lambda rid: {})
        assert entity.available
        assert publish.call_count == 2
        api._set_connected(False)
        assert not entity.available
        await entity.async_remove()
    assert api._report_listeners == {}
    assert api._connection_state_listeners == set()


@pytest.mark.parametrize(
    ("domain", "factory", "capability", "attribute", "expected"),
    [
        pytest.param(
            "sensor",
            _create_sensor_entities,
            "error_id",
            "native_value",
            None,
            id="sensor-unknown",
        ),
        pytest.param(
            "binary_sensor",
            _create_binary_sensor_entities,
            "ot_dhw_enabled",
            "is_on",
            None,
            id="binary-sensor-unknown",
        ),
        pytest.param(
            "switch",
            _create_switch_entities,
            "comfort_mode",
            "available",
            False,
            id="opentherm-switch",
        ),
        pytest.param(
            "button",
            _create_button_entities,
            "reset_boiler",
            "available",
            False,
            id="boiler-reset",
        ),
        pytest.param(
            "button",
            _create_button_entities,
            "reset_device",
            "available",
            True,
            id="device-reset",
        ),
        pytest.param(
            "sensor",
            _create_sensor_entities,
            "output_type",
            "native_value",
            "on_off",
            id="output-sensor",
        ),
    ],
)
async def test_output_change_published_immediately(
    hass: HomeAssistant,
    domain: str,
    factory: Callable[[ZentralyDevice], list[Entity]],
    capability: str,
    attribute: str,
    expected: bool | str | None,
) -> None:
    """Existing entities react to an output-only report without polling."""
    api = ZentralyApi("192.168.1.42", 80, "password", "ZTTWZ0100000001")
    api._set_connected(True)
    device = create_device(api, "ZTBIN0100000001", "bb")
    device.set_output_type(ZentralyOutputType.OPENTHERM)
    entity = next(
        entity for entity in factory(device) if entity.translation_key == capability
    )
    entity.hass = hass
    entity.entity_id = f"{domain}.zentraly_test"
    component = EntityComponent(logging.getLogger(__name__), domain, hass)
    with (
        patch.object(entity, "async_write_ha_state") as publish,
        patch.object(api, "async_execute_command") as execute,
    ):
        await component.async_add_entities([entity])
        publish.reset_mock()
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "bb", "ep": 1, "cluster": 65535, "id": 1000, "val": 0}
                ],
            }
        )
        assert getattr(entity, attribute) == expected
        assert publish.called
        execute.assert_not_awaited()
        api._handle_report(
            {
                "cmd": "report",
                "data": [
                    {"mac": "bb", "ep": 1, "cluster": 65535, "id": 1000, "val": 1}
                ],
            }
        )
        assert entity.available
        await entity.async_remove()
    assert api._report_listeners == {}
