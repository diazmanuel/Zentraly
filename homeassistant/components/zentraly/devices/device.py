"""Zentraly device definitions."""

from enum import Enum
from typing import TypedDict


class DeviceType(Enum):
    """Supported Zentraly device types."""

    CLIMATE = "climate"
    SWITCH = "switch"
    MONITOR = "monitor"
    UNKNOWN = "unknown"


class DeviceModel(Enum):
    """Supported Zentraly device models."""

    ZTTIN = "zttin"
    ZTBIN = "ztbin"
    UNKNOWN = "unknown"


class DeviceDefinition(TypedDict):
    """Definition of a supported Zentraly device."""

    type: DeviceType
    model: DeviceModel
    allowed_child_models: frozenset[DeviceModel]
    max_children: int


DEVICE_PREFIXES: dict[str, DeviceDefinition] = {
    "ZTTIN": {
        "type": DeviceType.CLIMATE,
        "model": DeviceModel.ZTTIN,
        "allowed_child_models": frozenset(
            {
                DeviceModel.ZTBIN,
            }
        ),
        "max_children": 1,
    },
    "ZTBIN": {
        "type": DeviceType.MONITOR,
        "model": DeviceModel.ZTBIN,
        "allowed_child_models": frozenset(),
        "max_children": 0,
    },
}


ZEROCONF_SUPPORTED_MODELS: frozenset[DeviceModel] = frozenset(
    {
        DeviceModel.ZTTIN,
    }
)


def get_device_definition(
    device_id: str,
) -> DeviceDefinition | None:
    """Return the Zentraly device definition for a device ID."""

    prefix = device_id[:5]

    return DEVICE_PREFIXES.get(prefix)


def get_device_type(device_id: str) -> DeviceType:
    """Return the Zentraly device type for a device ID."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return DeviceType.UNKNOWN

    return device_info["type"]


def get_device_model(device_id: str) -> DeviceModel:
    """Return the Zentraly device model for a device ID."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return DeviceModel.UNKNOWN

    return device_info["model"]


def supports_zeroconf_setup(device_id: str) -> bool:
    """Return whether a device supports direct Zeroconf setup."""

    return get_device_model(device_id) in ZEROCONF_SUPPORTED_MODELS


def supports_child_devices(device_id: str) -> bool:
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


def get_max_child_devices(device_id: str) -> int:
    """Return the maximum number of child devices."""

    device_info = get_device_definition(device_id)

    if device_info is None:
        return 0

    return device_info["max_children"]
