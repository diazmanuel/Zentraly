"""Models for the Zentraly integration."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .api import CommandResult, ConnectionStateListener, ReportListener, ZentralyApi
from .commands.base import ZentralyDeviceCommands
from .const import DOMAIN
from .devices.device import DeviceModel, DeviceType


@dataclass(slots=True)
class ZentralyDevice:
    """Runtime representation of a Zentraly device."""

    api: ZentralyApi
    device_id: str
    mac: str
    device_type: DeviceType
    device_model: DeviceModel
    commands: ZentralyDeviceCommands
    via_device_id: str | None = None

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
            manufacturer="Zentraly",
            model=self.model,
            name=self.device_id,
            configuration_url=self.configuration_url,
        )

        if self.via_device_id is not None:
            device_info["via_device_id"] = self.via_device_id

        return device_info

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
