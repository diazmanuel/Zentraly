"""Zentraly device definitions."""

from enum import Enum
from typing import TypedDict

from homeassistant.const import Platform


class DeviceModel(Enum):
    """Supported Zentraly device models."""

    ZTTIN = "zttin"
    ZTBIN = "ztbin"
    ZTTWZ = "zttwz"
    ZTREA = "ztrea"
    ZTEIM = "zteim"
    ZTIKD = "ztikd"
    ZTIKS = "ztiks"
    UNKNOWN = "unknown"


class DeviceDefinition(TypedDict):
    """Definition of a supported Zentraly device."""

    model: DeviceModel
    commercial_name: str
    platforms: frozenset[Platform]
    supports_zeroconf: bool
    allowed_child_models: frozenset[DeviceModel]
    max_children: int


DEVICE_PREFIXES: dict[str, DeviceDefinition] = {
    "ZTTIN": {
        "model": DeviceModel.ZTTIN,
        "commercial_name": "Termostato Inalámbrico Wi-Fi",
        "platforms": frozenset(
            {
                Platform.BUTTON,
                Platform.CLIMATE,
                Platform.SWITCH,
            }
        ),
        "supports_zeroconf": True,
        "allowed_child_models": frozenset(
            {
                DeviceModel.ZTBIN,
            }
        ),
        "max_children": 1,
    },
    "ZTBIN": {
        "model": DeviceModel.ZTBIN,
        "commercial_name": "Boiler Inalámbrico",
        "platforms": frozenset(
            {
                Platform.BINARY_SENSOR,
                Platform.BUTTON,
                Platform.SENSOR,
                Platform.SWITCH,
            }
        ),
        "supports_zeroconf": False,
        "allowed_child_models": frozenset(),
        "max_children": 0,
    },
    "ZTTWZ": {
        "model": DeviceModel.ZTTWZ,
        "commercial_name": "Termostato Wi-Fi Zentraly Home",
        "platforms": frozenset(
            {
                Platform.BINARY_SENSOR,
                Platform.BUTTON,
                Platform.CLIMATE,
                Platform.SENSOR,
                Platform.SWITCH,
            }
        ),
        "supports_zeroconf": True,
        "allowed_child_models": frozenset(),
        "max_children": 0,
    },
    "ZTREA": {
        "model": DeviceModel.ZTREA,
        "commercial_name": "Radiador electrico",
        "platforms": frozenset(
            {
                Platform.BUTTON,
                Platform.CLIMATE,
                Platform.SENSOR,
                Platform.SWITCH,
            }
        ),
        "supports_zeroconf": True,
        "allowed_child_models": frozenset(),
        "max_children": 0,
    },
    "ZTEIM": {
        "model": DeviceModel.ZTEIM,
        "commercial_name": "Enchufe zentraly mini",
        "platforms": frozenset(
            {
                Platform.BUTTON,
                Platform.NUMBER,
                Platform.SELECT,
                Platform.SENSOR,
                Platform.SWITCH,
            }
        ),
        "supports_zeroconf": True,
        "allowed_child_models": frozenset(),
        "max_children": 0,
    },
    "ZTIKD": {
        "model": DeviceModel.ZTIKD,
        "commercial_name": "Smart Switch Kinetic dual Wi-Fi",
        "platforms": frozenset(
            {
                Platform.BUTTON,
                Platform.NUMBER,
                Platform.SELECT,
                Platform.SENSOR,
                Platform.SWITCH,
            }
        ),
        "supports_zeroconf": True,
        "allowed_child_models": frozenset(),
        "max_children": 0,
    },
    "ZTIKS": {
        "model": DeviceModel.ZTIKS,
        "commercial_name": "Smart Switch Kinetic Simple Wi-Fi",
        "platforms": frozenset(
            {
                Platform.BUTTON,
                Platform.NUMBER,
                Platform.SELECT,
                Platform.SENSOR,
                Platform.SWITCH,
            }
        ),
        "supports_zeroconf": True,
        "allowed_child_models": frozenset(),
        "max_children": 0,
    },
}


def get_device_definition(
    device_id: str,
) -> DeviceDefinition | None:
    """Return the Zentraly device definition for a device ID."""

    prefix = device_id[:5]

    return DEVICE_PREFIXES.get(prefix)


def get_device_model(
    device_id: str,
) -> DeviceModel:
    """Return the Zentraly device model for a device ID."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return DeviceModel.UNKNOWN

    return device_info["model"]


def get_device_platforms(
    device_id: str,
) -> frozenset[Platform]:
    """Return the Home Assistant platforms for a Zentraly device."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return frozenset()

    return device_info["platforms"]


def supports_zeroconf_setup(
    device_id: str,
) -> bool:
    """Return whether a device supports direct Zeroconf setup."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return False

    return device_info["supports_zeroconf"]


def supports_child_devices(
    device_id: str,
) -> bool:
    """Return whether a Zentraly device supports child devices."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return False

    return bool(device_info["allowed_child_models"])


def is_allowed_child_device(
    parent_device_id: str,
    child_device_id: str,
) -> bool:
    """Return whether a device model is allowed as a child."""

    parent_info = get_device_definition(parent_device_id)

    if parent_info is None:
        return False

    child_model = get_device_model(child_device_id)

    if child_model is DeviceModel.UNKNOWN:
        return False

    return child_model in parent_info["allowed_child_models"]


def get_max_child_devices(
    device_id: str,
) -> int:
    """Return the maximum number of child devices."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return 0

    return device_info["max_children"]
