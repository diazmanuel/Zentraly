"""Models for the Zentraly integration."""

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .api import CommandResult, ConnectionStateListener, ReportListener, ZentralyApi
from .commands.base import ZentralyDeviceCommands
from .commands.protocol import ResponseStatus
from .const import DOMAIN
from .device_classes.sensor.capabilities import SensorCapability
from .device_classes.types import ZentralyOutputType
from .devices.device import DeviceModel
from .exceptions import (
    ZentralyCommandRejectedError,
    ZentralyConnectionError,
    ZentralyInvalidResponseError,
    ZentralyValidationError,
)

_LOGGER = logging.getLogger(__name__)

type ActionStateListener = Callable[[dict[object, Any]], None]


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
    _responding: bool = field(default=True, init=False)
    _action_state_listeners: dict[int, set[ActionStateListener]] = field(
        default_factory=dict, init=False
    )
    _state_listeners: set[Callable[[], None]] = field(default_factory=set, init=False)
    _report_listeners: set[ReportListener] = field(default_factory=set, init=False)
    _remove_report_listener: Callable[[], None] | None = field(default=None, init=False)

    @property
    def available(self) -> bool:
        """Return whether the gateway and this device can communicate."""
        return self.connected and self._responding

    def set_output_type(self, value: ZentralyOutputType) -> None:
        """Update shared output state and notify dependent entities."""
        if self.output_type is value:
            return
        self.output_type = value
        self._notify_state()

    def _notify_state(self) -> None:
        """Publish a shared device state change."""
        for listener in tuple(self._state_listeners):
            listener()

    def _set_responding(self, responding: bool) -> None:
        """Track device reachability separately from the gateway transport."""
        if self._responding == responding:
            return
        self._responding = responding
        if responding:
            _LOGGER.info(
                "Zentraly device responding again: device_id=%s mac=%s",
                self.device_id,
                self.mac,
            )
        else:
            _LOGGER.warning(
                "Zentraly device not responding: device_id=%s mac=%s",
                self.device_id,
                self.mac,
            )
        self._notify_state()

    def add_state_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to shared availability and output changes."""
        self._state_listeners.add(listener)
        self._ensure_report_listener()

        def remove_listener() -> None:
            self._state_listeners.discard(listener)
            self._remove_unused_report_listener()

        return remove_listener

    def _ensure_report_listener(self) -> None:
        """Subscribe once for shared state and capability reports."""
        if self._remove_report_listener is None:
            self._remove_report_listener = self.api.add_report_listener(
                self.mac, self._handle_report
            )

    def _remove_unused_report_listener(self) -> None:
        """Release the subscription after the last entity is removed."""
        if (
            not self._state_listeners
            and not self._report_listeners
            and self._remove_report_listener is not None
        ):
            self._remove_report_listener()
            self._remove_report_listener = None

    def _handle_report(self, report_data: list[dict[str, Any]]) -> None:
        """Apply shared state before dispatching capability updates."""
        for entry in report_data:
            endpoint = entry.get("ep")
            if (
                type(endpoint) is not int
                or endpoint not in self.commands.channel_endpoints
            ):
                continue
            parser = getattr(
                self.commands.for_endpoint(endpoint), "parse_report_entry", None
            )
            if not callable(parser):
                continue
            try:
                result = parser(entry)
            except TypeError, ValueError:
                continue
            if result is None:
                continue
            capability, value = result
            if not self.supports(capability):
                continue
            self._set_responding(True)
            if capability is SensorCapability.OUTPUT_TYPE and isinstance(
                value, ZentralyOutputType
            ):
                self.set_output_type(value)
        for listener in tuple(self._report_listeners):
            listener(report_data)

    def add_action_state_listener(
        self,
        endpoint: int,
        listener: ActionStateListener,
    ) -> Callable[[], None]:
        """Subscribe to confirmed action effects on a channel."""
        self._action_state_listeners.setdefault(endpoint, set()).add(listener)

        def remove_listener() -> None:
            listeners = self._action_state_listeners.get(endpoint)
            if listeners is not None:
                listeners.discard(listener)
                if not listeners:
                    del self._action_state_listeners[endpoint]

        return remove_listener

    def notify_action_state(self, endpoint: int, updates: dict[object, Any]) -> None:
        """Publish model-defined effects only after a successful action."""
        for listener in tuple(self._action_state_listeners.get(endpoint, ())):
            listener(updates)

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

        self._report_listeners.add(listener)
        self._ensure_report_listener()

        def remove_listener() -> None:
            self._report_listeners.discard(listener)
            self._remove_unused_report_listener()

        return remove_listener

    async def async_execute_command(
        self,
        command_builder: Callable[[int], dict[str, Any]],
    ) -> CommandResult | None:
        """Execute a command using the shared Zentraly connection."""

        result = await self.api.async_execute_command(
            command_builder,
        )
        if self.connected:
            if result is None:
                self._set_responding(False)
            elif result[1].get("status") == ResponseStatus.SUCCESS:
                self._set_responding(True)
        return result

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
