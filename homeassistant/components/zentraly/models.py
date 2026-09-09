"""Models for the Zentraly integration."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .api import CommandResult, ConnectionStateListener, ReportListener, ZentralyApi
from .commands.base import ZentralyDeviceCommands
from .commands.protocol import ResponseStatus
from .const import DOMAIN
from .device_classes.types import ZentralyOutputType
from .devices.device import DeviceModel
from .exceptions import (
    ZentralyCommandRejectedError,
    ZentralyConnectionError,
    ZentralyInvalidResponseError,
    ZentralyValidationError,
)


@dataclass(slots=True)
class ZentralyDevice:
    """Runtime representation of a Zentraly device."""

    api: ZentralyApi
    device_id: str
    mac: str
    device_model: DeviceModel
    commands: ZentralyDeviceCommands
    via_device_id: str | None = None

    output_type: ZentralyOutputType | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None

    @property
    def connected(self) -> bool:
        """Return the shared gateway connection state."""

        return self.api.connected

    @property
    def model(self) -> str:
        """Return the device model name."""

        return self.device_model.value

    @property
    def configuration_url(self) -> str:
        """Return the configuration URL of the shared Zentraly gateway."""

        return f"http://{self.api.host}:{self.api.port}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device information."""

        device_info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    self.device_id,
                )
            },
            connections={
                (
                    dr.CONNECTION_NETWORK_MAC,
                    self.mac,
                )
            },
            manufacturer="Zentraly",
            model=self.model,
            name=self.device_id,
            serial_number=self.device_id,
            configuration_url=self.configuration_url,
        )

        if self.firmware_version is not None:
            device_info["sw_version"] = self.firmware_version

        if self.hardware_version is not None:
            device_info["hw_version"] = self.hardware_version

        if self.via_device_id is not None:
            device_info["via_device_id"] = self.via_device_id

        return device_info

    @property
    def opentherm_connected(self) -> bool:
        """Return whether the device is using OpenTherm."""

        return self.output_type is ZentralyOutputType.OPENTHERM

    def supports(
        self,
        capability: object,
    ) -> bool:
        """Return whether the device supports a capability."""

        capabilities: frozenset[object] = getattr(
            self.commands,
            "capabilities",
            frozenset(),
        )

        return capability in capabilities

    def add_connection_state_listener(
        self,
        listener: ConnectionStateListener,
    ) -> Callable[[], None]:
        """Register a shared connection-state listener."""

        return self.api.add_connection_state_listener(listener)

    def add_report_listener(
        self,
        listener: ReportListener,
    ) -> Callable[[], None]:
        """Register a report listener for this device."""

        return self.api.add_report_listener(
            self.mac,
            listener,
        )

    async def async_execute_command(
        self,
        command_builder: Callable[[int], dict[str, Any]],
    ) -> CommandResult | None:
        """Execute a command using the shared Zentraly connection."""

        return await self.api.async_execute_command(
            command_builder,
        )

    async def async_execute_action_command(
        self,
        command_builder: Callable[[int], dict[str, Any]],
    ) -> CommandResult:
        """Execute an action command, preserving its failure category."""

        def build(rid: int) -> dict[str, Any]:
            try:
                return command_builder(rid)
            except (TypeError, ValueError) as err:
                raise ZentralyValidationError("Invalid command parameters") from err

        result = await self.async_execute_command(build)
        if result is None:
            raise ZentralyConnectionError("No response to action command")

        _, response = result
        status = response.get("status")
        if type(status) is not int:
            raise ZentralyInvalidResponseError("Missing or invalid response status")
        if status != ResponseStatus.SUCCESS:
            raise ZentralyCommandRejectedError(f"Command rejected with status {status}")
        return result


@dataclass(slots=True)
class ZentralyData:
    """Runtime data for Zentraly."""

    api: ZentralyApi
    device: ZentralyDevice
    children: dict[str, ZentralyDevice] = field(default_factory=dict)

    def get_child(
        self,
        subentry_id: str,
    ) -> ZentralyDevice | None:
        """Return a child device by config subentry ID."""

        return self.children.get(subentry_id)


type ZentralyConfigEntry = ConfigEntry[ZentralyData]
