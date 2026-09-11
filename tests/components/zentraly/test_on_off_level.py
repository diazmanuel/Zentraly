"""Tests for the shared 65006/0 on/off level."""

import pytest

from homeassistant.components.zentraly.device_classes.binary_sensor.capabilities import (
    BinarySensorCapability,
)
from homeassistant.components.zentraly.device_classes.climate.capabilities import (
    ClimateCapability,
)
from homeassistant.components.zentraly.device_classes.switch.capabilities import (
    SwitchCapability,
)
from homeassistant.components.zentraly.devices import get_device_commands
from homeassistant.components.zentraly.devices.device import DeviceModel

ON_OFF_CASES = [
    pytest.param(
        DeviceModel.ZTTIN,
        "parse_heat_demand_response",
        ClimateCapability.HEAT_DEMAND,
        id="zttin-heat-demand",
    ),
    pytest.param(
        DeviceModel.ZTBIN,
        "parse_boiler_on_response",
        BinarySensorCapability.BOILER_ON,
        id="ztbin-boiler",
    ),
    pytest.param(
        DeviceModel.ZTTWZ,
        "parse_boiler_on_response",
        BinarySensorCapability.BOILER_ON,
        id="zttwz-validation",
    ),
    pytest.param(
        DeviceModel.ZTEIM,
        "parse_power_state_response",
        SwitchCapability.POWER,
        id="zteim-power",
    ),
    pytest.param(
        DeviceModel.ZTIKD,
        "parse_power_state_response",
        SwitchCapability.POWER,
        id="ztikd-power",
    ),
    pytest.param(
        DeviceModel.ZTIKS,
        "parse_power_state_response",
        SwitchCapability.POWER,
        id="ztiks-power",
    ),
]


@pytest.mark.parametrize(("model", "parser_name", "capability"), ON_OFF_CASES)
@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        pytest.param(0, False, id="off"),
        pytest.param(1, True, id="one"),
        pytest.param(50, True, id="intermediate"),
        pytest.param(100, True, id="maximum"),
    ],
)
def test_on_off_level(
    model: DeviceModel,
    parser_name: str,
    capability: BinarySensorCapability | ClimateCapability | SwitchCapability,
    raw_value: int,
    expected: bool,
) -> None:
    """Read responses and reports agree for every model using 65006/0."""
    commands = get_device_commands(model)
    assert (
        getattr(commands, parser_name)(
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": 0, "val": raw_value}],
            },
            1,
        )
        is expected
    )
    assert commands.parse_report_entry(
        {"cluster": 65006, "ep": 1, "id": 0, "val": raw_value}
    ) == (capability, expected)


@pytest.mark.parametrize(("model", "parser_name", "capability"), ON_OFF_CASES)
@pytest.mark.parametrize(
    ("raw_value", "error"),
    [
        pytest.param(-1, ValueError, id="negative"),
        pytest.param(101, ValueError, id="above-maximum"),
        pytest.param(1.5, TypeError, id="float"),
        pytest.param("50", TypeError, id="string"),
        pytest.param(None, TypeError, id="null"),
        pytest.param(True, TypeError, id="boolean"),
    ],
)
def test_invalid_on_off_level(
    model: DeviceModel,
    parser_name: str,
    capability: BinarySensorCapability | ClimateCapability | SwitchCapability,
    raw_value: float | str | None,
    error: type[Exception],
) -> None:
    """Reject invalid levels in both parsing paths."""
    commands = get_device_commands(model)
    with pytest.raises(error):
        getattr(commands, parser_name)(
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": 0, "val": raw_value}],
            },
            1,
        )
    with pytest.raises(error):
        commands.parse_report_entry(
            {"cluster": 65006, "ep": 1, "id": 0, "val": raw_value}
        )


@pytest.mark.parametrize("model", [DeviceModel.ZTBIN, DeviceModel.ZTTWZ])
@pytest.mark.parametrize("raw_value", [50, 100])
def test_child_validation_level(model: DeviceModel, raw_value: int) -> None:
    """Child validation accepts the full level range, including unused states."""
    commands = get_device_commands(model)
    command = commands.build_validation_command(1, "001122334455")
    assert command["cluster"] == 65006
    assert command["attrs"][0]["id"] == 0
    commands.parse_validation_response(
        {
            "cmd": "readAttr",
            "rid": 1,
            "status": 200,
            "attrs": [{"id": 0, "val": raw_value}],
        },
        1,
    )


@pytest.mark.parametrize("model", [DeviceModel.ZTTWZ, DeviceModel.ZTREA])
def test_thermostat_heat_demand_remains_binary(model: DeviceModel) -> None:
    """Cluster 65513/6 still rejects non-binary values."""
    commands = get_device_commands(model)
    with pytest.raises(ValueError):
        commands.parse_heat_demand_response(
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": 6, "val": 50}],
            },
            1,
        )
    with pytest.raises(ValueError):
        commands.parse_report_entry({"cluster": 65513, "ep": 1, "id": 6, "val": 50})


@pytest.mark.parametrize(
    ("model", "parser_name", "attribute_id"),
    [
        pytest.param(
            DeviceModel.ZTTIN, "parse_child_lock_response", 90, id="child-lock"
        ),
        pytest.param(
            DeviceModel.ZTBIN, "parse_forced_mode_response", 2, id="forced-mode"
        ),
        pytest.param(
            DeviceModel.ZTEIM,
            "parse_return_to_crono_response",
            29,
            id="return-to-crono",
        ),
    ],
)
def test_other_switches_remain_binary(
    model: DeviceModel, parser_name: str, attribute_id: int
) -> None:
    """The extended level range does not apply to other switch attributes."""
    commands = get_device_commands(model)
    with pytest.raises(ValueError):
        getattr(commands, parser_name)(
            {
                "cmd": "readAttr",
                "rid": 1,
                "status": 200,
                "attrs": [{"id": attribute_id, "val": 50}],
            },
            1,
        )
