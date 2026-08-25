"""Zentraly device implementations."""

from ..commands.base import ZentralyDeviceCommands
from .device import DeviceModel
from .ztbin import ZtbinCommands
from .zttin import ZttinCommands


def get_device_commands(
    device_model: DeviceModel,
) -> ZentralyDeviceCommands:
    """Return the commands implementation for a device model."""

    if device_model is DeviceModel.ZTTIN:
        return ZttinCommands()

    if device_model is DeviceModel.ZTBIN:
        return ZtbinCommands()

    raise ValueError(f"Unsupported Zentraly device model: {device_model}")
