"""Zentraly device implementations."""

from ..commands.base import ZentralyDeviceCommands
from .device import DeviceModel
from .ztbin import ZtbinCommands
from .zttin import ZttinCommands

DEVICE_COMMANDS: dict[
    DeviceModel,
    type[ZentralyDeviceCommands],
] = {
    DeviceModel.ZTTIN: ZttinCommands,
    DeviceModel.ZTBIN: ZtbinCommands,
}


def get_device_commands(
    device_model: DeviceModel,
) -> ZentralyDeviceCommands:
    """Return the commands implementation for a device model."""

    command_class = DEVICE_COMMANDS.get(device_model)

    if command_class is None:
        raise ValueError(f"Unsupported Zentraly device model: {device_model}")

    return command_class()
