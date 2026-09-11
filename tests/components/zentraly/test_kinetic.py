"""Tests for the kinetic switch command contract."""

import math
from typing import Any

import pytest

from homeassistant.components.zentraly.commands.protocol import DataType
from homeassistant.components.zentraly.device_classes.types import SelectOperationMode
from homeassistant.components.zentraly.devices import get_device_commands
from homeassistant.components.zentraly.devices.device import DeviceModel
from homeassistant.components.zentraly.devices.ztikd import ZtikdCommands
from homeassistant.components.zentraly.devices.ztiks import ZtiksCommands

MAC = "aabbccddeeff"


@pytest.fixture(
    params=[
        pytest.param(ZtikdCommands, id="dual"),
        pytest.param(ZtiksCommands, id="single"),
    ]
)
def commands(request: pytest.FixtureRequest) -> ZtikdCommands | ZtiksCommands:
    """Return a real implementation for each kinetic model."""
    return request.param()


@pytest.mark.parametrize(
    ("model", "endpoints"),
    [
        pytest.param(DeviceModel.ZTIKD, (1, 2), id="dual"),
        pytest.param(DeviceModel.ZTIKS, (1,), id="single"),
    ],
)
def test_registered_channels(model: DeviceModel, endpoints: tuple[int, ...]) -> None:
    """The model registry exposes the physical device's channel count."""
    assert get_device_commands(model).channel_endpoints == endpoints


@pytest.mark.parametrize("endpoint", [0, 3, True, "1"])
def test_invalid_endpoint(
    commands: ZtikdCommands | ZtiksCommands, endpoint: int | str
) -> None:
    """Reject channel selections that cannot be addressed."""
    with pytest.raises(ValueError):
        commands.for_endpoint(endpoint)


def test_single_has_no_second_channel() -> None:
    """A single channel model cannot send commands to endpoint two."""
    with pytest.raises(ValueError):
        ZtiksCommands().for_endpoint(2)


@pytest.mark.parametrize(
    ("name", "attribute", "cluster", "data_type", "raw", "expected"),
    [
        pytest.param(
            "firmware_version",
            2,
            65000,
            DataType.CHAR_STRING,
            "1.2.3",
            "1.2.3",
            id="firmware",
        ),
        pytest.param(
            "hardware_version", 3, 65000, DataType.CHAR_STRING, "2", "2", id="hardware"
        ),
        pytest.param(
            "wifi_signal_power", 100, 65534, DataType.INT16, -55, -55, id="wifi"
        ),
        pytest.param("power_state", 0, 65006, DataType.INT16, 50, True, id="power"),
        pytest.param(
            "return_to_crono",
            29,
            65006,
            DataType.INT16,
            1,
            True,
            id="return-to-schedule",
        ),
        pytest.param(
            "timer_off_enable", 50, 65006, DataType.INT16, 0, False, id="timer-enable"
        ),
        pytest.param(
            "operation_mode",
            28,
            65006,
            DataType.INT16,
            2,
            SelectOperationMode.AUTO,
            id="mode",
        ),
        pytest.param("timer_off", 51, 65006, DataType.INT16, 179, 2.0, id="duration"),
    ],
)
def test_attribute_reads(
    commands: ZtikdCommands | ZtiksCommands,
    name: str,
    attribute: int,
    cluster: int,
    data_type: DataType,
    raw: int | str,
    expected: bool | str | float | SelectOperationMode,
) -> None:
    """Read commands and decoders match the documented attribute contract."""
    assert getattr(commands, f"build_read_{name}")(7, MAC) == {
        "cmd": "readAttr",
        "rid": 7,
        "mac": MAC,
        "cluster": cluster,
        "ep": 1,
        "attrs": [{"id": attribute, "type": data_type}],
    }
    assert (
        getattr(commands, f"parse_{name}_response")(
            {
                "cmd": "readAttr",
                "rid": 7,
                "status": 200,
                "attrs": [{"id": attribute, "val": raw}],
            },
            7,
        )
        == expected
    )


def test_discovery_and_shared_information(
    commands: ZtikdCommands | ZtiksCommands,
) -> None:
    """MAC discovery and reset always address the physical device."""
    assert commands.get_mac_command(7) == {
        "cmd": "readAttr",
        "rid": 7,
        "mac": "",
        "cluster": 65000,
        "ep": 1,
        "attrs": [{"id": 20, "type": DataType.CHAR_STRING}],
    }
    assert (
        commands.parse_mac_response(
            {
                "cmd": "readAttr",
                "rid": 7,
                "status": 200,
                "attrs": [{"id": 20, "val": MAC}],
            },
            7,
        )
        == MAC
    )
    assert commands.build_reset_device(7, MAC) == {
        "cmd": "writeAttr",
        "rid": 7,
        "mac": MAC,
        "cluster": 65000,
        "ep": 1,
        "attrs": [{"id": 12, "type": DataType.INT16, "val": 1}],
    }


@pytest.mark.parametrize(
    "name", ["firmware_version", "hardware_version", "wifi_signal_power"]
)
def test_shared_reads_on_second_channel(name: str) -> None:
    """Device-wide reads stay on endpoint one even from a bound channel."""
    commands = ZtikdCommands().for_endpoint(2)
    assert getattr(commands, f"build_read_{name}")(7, MAC)["ep"] == 1
    assert commands.get_mac_command(7)["ep"] == 1
    assert commands.build_reset_device(7, MAC)["ep"] == 1


@pytest.mark.parametrize(
    ("raw", "minutes"),
    [
        pytest.param(60, 1.0, id="minimum"),
        pytest.param(119, 1.0, id="truncate"),
        pytest.param(59, 0.0, id="discard-subminute-seconds"),
        pytest.param(1860, 31.0, id="read-outside-write-range"),
        pytest.param(1800, 30.0, id="maximum"),
    ],
)
def test_duration_read(
    commands: ZtikdCommands | ZtiksCommands, raw: int, minutes: float
) -> None:
    """Read the configured duration without a countdown or bit decoding."""
    assert (
        commands.parse_timer_off_response(
            {
                "cmd": "readAttr",
                "rid": 7,
                "status": 200,
                "attrs": [{"id": 51, "val": raw}],
            },
            7,
        )
        == minutes
    )
    assert (
        commands.parse_report_entry({"ep": 1, "cluster": 65006, "id": 51, "val": raw})[
            1
        ]
        == minutes
    )


@pytest.mark.parametrize("minutes", [1.0, 30.0])
@pytest.mark.parametrize("endpoint", [1, 2])
def test_duration_write(endpoint: int, minutes: float) -> None:
    """Write exactly one plain-seconds attribute on the selected channel."""
    commands = ZtikdCommands().for_endpoint(endpoint)
    assert commands.build_write_timer_off(7, MAC, minutes) == {
        "cmd": "writeAttr",
        "rid": 7,
        "mac": MAC,
        "cluster": 65006,
        "ep": endpoint,
        "attrs": [{"id": 51, "type": DataType.INT16, "val": int(minutes) * 60}],
    }


@pytest.mark.parametrize("minutes", [0, -1, 31, 1.5, math.nan, math.inf])
def test_invalid_duration_write(
    commands: ZtikdCommands | ZtiksCommands, minutes: float
) -> None:
    """Reject invalid duration conversion inputs before sending."""
    with pytest.raises(ValueError):
        commands.build_write_timer_off(7, MAC, minutes)


@pytest.mark.parametrize(
    ("name", "attribute", "value"),
    [
        pytest.param("timer_off", 51, 0, id="zero-duration"),
        pytest.param("timer_off", 51, -60, id="negative-duration"),
        pytest.param("timer_off", 51, "60", id="string-duration"),
        pytest.param("timer_off", 51, True, id="boolean-duration"),
        pytest.param("timer_off_enable", 50, 2, id="invalid-enable"),
        pytest.param("return_to_crono", 29, 50, id="invalid-return"),
        pytest.param("operation_mode", 28, 9, id="unsupported-mode"),
        pytest.param("power_state", 0, 101, id="invalid-level"),
        pytest.param("firmware_version", 2, "", id="empty-version"),
        pytest.param("mac", 20, None, id="missing-mac"),
    ],
)
def test_invalid_read_values(
    commands: ZtikdCommands | ZtiksCommands, name: str, attribute: int, value: Any
) -> None:
    """Malformed device values do not become a valid state."""
    with pytest.raises((TypeError, ValueError)):
        getattr(commands, f"parse_{name}_response")(
            {
                "cmd": "readAttr",
                "rid": 7,
                "status": 200,
                "attrs": [{"id": attribute, "val": value}],
            },
            7,
        )


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(
            {"cmd": "readAttr", "rid": 7, "status": 200, "attrs": []}, id="absent"
        ),
        pytest.param(
            {"cmd": "readAttr", "rid": 7, "status": 200, "attrs": [{"id": 51}]},
            id="missing-value",
        ),
        pytest.param(
            {
                "cmd": "readAttr",
                "rid": 8,
                "status": 200,
                "attrs": [{"id": 51, "val": 60}],
            },
            id="wrong-rid",
        ),
        pytest.param(
            {
                "cmd": "readAttr",
                "rid": 7,
                "status": 400,
                "attrs": [{"id": 51, "val": 60}],
            },
            id="rejected",
        ),
    ],
)
def test_incomplete_read_response(
    commands: ZtikdCommands | ZtiksCommands, response: dict[str, Any]
) -> None:
    """A stale or incomplete response must not update a duration."""
    with pytest.raises(ValueError):
        commands.parse_timer_off_response(response, 7)


@pytest.mark.parametrize("mode", [SelectOperationMode.OFF, SelectOperationMode.TIMER])
def test_invalid_mode_write(
    commands: ZtikdCommands | ZtiksCommands, mode: SelectOperationMode
) -> None:
    """Kinetic switches cannot select the ZTEIM countdown mode."""
    with pytest.raises(ValueError):
        commands.build_write_operation_mode(7, MAC, mode)


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(
            {"ep": "1", "cluster": 65006, "id": 0, "val": 1}, id="invalid-endpoint"
        ),
        pytest.param(
            {"ep": 1, "cluster": "65006", "id": 0, "val": 1}, id="invalid-cluster"
        ),
        pytest.param(
            {"ep": 1, "cluster": 65006, "id": "0", "val": 1}, id="invalid-attribute"
        ),
        pytest.param(
            {"ep": 1, "cluster": 65006, "id": 99, "val": 1}, id="unknown-attribute"
        ),
        pytest.param({"ep": 1, "cluster": 1, "id": 0, "val": 1}, id="unknown-cluster"),
    ],
)
def test_unsupported_report_entry(
    commands: ZtikdCommands | ZtiksCommands, entry: dict[str, Any]
) -> None:
    """Ignore malformed addressing and unknown attributes."""
    assert commands.parse_report_entry(entry) is None
