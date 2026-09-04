"""High-level API for Zentraly switch devices."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from ..sensor.capabilities import SensorCapability
from ..types import ZentralyOutputType
from .capabilities import SwitchCapability
from .command_protocols import (
    AlwaysOnDisplayCommands,
    AlwaysOnLedCommands,
    ChildLockCommands,
    ComfortModeCommands,
    ForcedModeCommands,
    HighPowerProtectionCommands,
    HighVoltageProtectionCommands,
    LowVoltageProtectionCommands,
    PowerCommands,
    ReturnToCronoCommands,
)

if TYPE_CHECKING:
    from ...models import ZentralyDevice

type SwitchStateUpdate = dict[SwitchCapability, Any]
type SwitchStateListener = Callable[[SwitchStateUpdate], None]
type SwitchReadBuilder = Callable[[int, str], dict[str, Any]]
type SwitchWriteBuilder = Callable[[int, str, bool], dict[str, Any]]
type SwitchReadParser = Callable[[dict[str, Any], int], bool]
type SwitchWriteParser = Callable[[dict[str, Any], int], None]

_OPENTHERM_CAPABILITIES = frozenset(
    {
        SwitchCapability.COMFORT_MODE,
    }
)


class ZentralySwitchApi:
    """High-level API for Zentraly switch devices."""

    def __init__(self, device: ZentralyDevice) -> None:
        """Initialize the switch API."""

        self._device = device

        self._state_listeners: set[SwitchStateListener] = set()
        self._remove_report_listener: Callable[[], None] | None = None

    @property
    def device(self) -> ZentralyDevice:
        """Return the underlying Zentraly device."""

        return self._device

    def supports(
        self,
        capability: SwitchCapability,
    ) -> bool:
        """Return whether the device supports a capability."""

        return self._device.supports(capability)

    def add_state_listener(
        self,
        listener: SwitchStateListener,
    ) -> Callable[[], None]:
        """Register a switch state update listener."""

        self._state_listeners.add(listener)

        if self._remove_report_listener is None:
            self._remove_report_listener = self._device.add_report_listener(
                self._handle_report
            )

        def remove_listener() -> None:
            """Remove the switch state listener."""

            self._state_listeners.discard(listener)

            if self._state_listeners:
                return

            if self._remove_report_listener is None:
                return

            self._remove_report_listener()
            self._remove_report_listener = None

        return remove_listener

    def _handle_report(
        self,
        report_data: list[dict[str, Any]],
    ) -> None:
        """Parse and dispatch switch updates from a device report."""

        parser = getattr(
            self._device.commands,
            "parse_report_entry",
            None,
        )

        if not callable(parser):
            return

        updates: SwitchStateUpdate = {}

        for entry in report_data:
            try:
                result = parser(entry)

            except TypeError, ValueError:
                continue

            if result is None:
                continue

            capability, value = result

            if capability is SensorCapability.OUTPUT_TYPE:
                if isinstance(value, ZentralyOutputType):
                    self._device.output_type = value

                continue

            if not isinstance(capability, SwitchCapability):
                continue

            if not self.supports(capability):
                continue

            if (
                capability in _OPENTHERM_CAPABILITIES
                and not self._device.opentherm_connected
            ):
                continue

            if not isinstance(value, bool):
                continue

            updates[capability] = value

        if not updates:
            return

        for listener in tuple(self._state_listeners):
            listener(updates)

    async def _async_get_switch_value(
        self,
        *,
        capability: SwitchCapability,
        builder: SwitchReadBuilder,
        parser: SwitchReadParser,
    ) -> bool | None:
        """Read a switch capability from the device."""

        if not self.supports(capability):
            return None

        if (
            capability in _OPENTHERM_CAPABILITIES
            and not self._device.opentherm_connected
        ):
            return None

        result = await self._device.async_execute_command(
            lambda rid: builder(
                rid,
                self._device.mac,
            )
        )

        if result is None:
            return None

        rid, response = result

        try:
            value = parser(
                response,
                rid,
            )

        except TypeError, ValueError:
            return None

        if not isinstance(value, bool):
            return None

        return value

    async def _async_set_switch_value(
        self,
        *,
        capability: SwitchCapability,
        builder: SwitchWriteBuilder,
        parser: SwitchWriteParser,
        enabled: bool,
    ) -> bool:
        """Write a switch capability to the device."""

        if not self.supports(capability):
            return False

        if (
            capability in _OPENTHERM_CAPABILITIES
            and not self._device.opentherm_connected
        ):
            return False

        result = await self._device.async_execute_command(
            lambda rid: builder(
                rid,
                self._device.mac,
                enabled,
            )
        )

        if result is None:
            return False

        rid, response = result

        try:
            parser(
                response,
                rid,
            )

        except TypeError, ValueError:
            return False

        return True

    async def async_get_power(
        self,
    ) -> bool | None:
        """Return the power state."""

        commands = cast(
            PowerCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.POWER,
            builder=commands.build_read_power_state,
            parser=commands.parse_power_state_response,
        )

    async def async_set_power(
        self,
        enabled: bool,
    ) -> bool:
        """Set the power state."""

        commands = cast(
            PowerCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.POWER,
            builder=commands.build_write_power_state,
            parser=commands.parse_write_power_state_response,
            enabled=enabled,
        )

    async def async_get_child_lock(
        self,
    ) -> bool | None:
        """Return the child-lock state."""

        commands = cast(
            ChildLockCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.CHILD_LOCK,
            builder=commands.build_read_child_lock,
            parser=commands.parse_child_lock_response,
        )

    async def async_set_child_lock(
        self,
        enabled: bool,
    ) -> bool:
        """Set the child-lock state."""

        commands = cast(
            ChildLockCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.CHILD_LOCK,
            builder=commands.build_write_child_lock,
            parser=commands.parse_write_child_lock_response,
            enabled=enabled,
        )

    async def async_get_always_on_display(
        self,
    ) -> bool | None:
        """Return the always-on display state."""

        commands = cast(
            AlwaysOnDisplayCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.ALWAYS_ON_DISPLAY,
            builder=commands.build_read_always_on_display,
            parser=commands.parse_always_on_display_response,
        )

    async def async_set_always_on_display(
        self,
        enabled: bool,
    ) -> bool:
        """Set the always-on display state."""

        commands = cast(
            AlwaysOnDisplayCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.ALWAYS_ON_DISPLAY,
            builder=commands.build_write_always_on_display,
            parser=commands.parse_write_always_on_display_response,
            enabled=enabled,
        )

    async def async_get_always_on_led(
        self,
    ) -> bool | None:
        """Return the always-on LED state."""

        commands = cast(
            AlwaysOnLedCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.ALWAYS_ON_LED,
            builder=commands.build_read_always_on_led,
            parser=commands.parse_always_on_led_response,
        )

    async def async_set_always_on_led(
        self,
        enabled: bool,
    ) -> bool:
        """Set the always-on LED state."""

        commands = cast(
            AlwaysOnLedCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.ALWAYS_ON_LED,
            builder=commands.build_write_always_on_led,
            parser=commands.parse_write_always_on_led_response,
            enabled=enabled,
        )

    async def async_get_comfort_mode(
        self,
    ) -> bool | None:
        """Return the OpenTherm comfort-mode state."""

        commands = cast(
            ComfortModeCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.COMFORT_MODE,
            builder=commands.build_read_comfort_mode,
            parser=commands.parse_comfort_mode_response,
        )

    async def async_set_comfort_mode(
        self,
        enabled: bool,
    ) -> bool:
        """Set the OpenTherm comfort-mode state."""

        commands = cast(
            ComfortModeCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.COMFORT_MODE,
            builder=commands.build_write_comfort_mode,
            parser=commands.parse_write_comfort_mode_response,
            enabled=enabled,
        )

    async def async_get_forced_mode(
        self,
    ) -> bool | None:
        """Return the forced-mode state."""

        commands = cast(
            ForcedModeCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.FORCED_MODE,
            builder=commands.build_read_forced_mode,
            parser=commands.parse_forced_mode_response,
        )

    async def async_set_forced_mode(
        self,
        enabled: bool,
    ) -> bool:
        """Set the forced-mode state."""

        commands = cast(
            ForcedModeCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.FORCED_MODE,
            builder=commands.build_write_forced_mode,
            parser=commands.parse_write_forced_mode_response,
            enabled=enabled,
        )

    async def async_get_return_to_crono(
        self,
    ) -> bool | None:
        """Return the return-to-crono state."""

        commands = cast(
            ReturnToCronoCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.RETURN_TO_CRONO,
            builder=commands.build_read_return_to_crono,
            parser=commands.parse_return_to_crono_response,
        )

    async def async_set_return_to_crono(
        self,
        enabled: bool,
    ) -> bool:
        """Set the return-to-crono state."""

        commands = cast(
            ReturnToCronoCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.RETURN_TO_CRONO,
            builder=commands.build_write_return_to_crono,
            parser=commands.parse_write_return_to_crono_response,
            enabled=enabled,
        )

    async def async_get_high_voltage_protection(
        self,
    ) -> bool | None:
        """Return the high-voltage-protection state."""

        commands = cast(
            HighVoltageProtectionCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.HIGH_VOLTAGE_PROTECTION,
            builder=commands.build_read_high_voltage_protection,
            parser=commands.parse_high_voltage_protection_response,
        )

    async def async_set_high_voltage_protection(
        self,
        enabled: bool,
    ) -> bool:
        """Set the high-voltage-protection state."""

        commands = cast(
            HighVoltageProtectionCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.HIGH_VOLTAGE_PROTECTION,
            builder=commands.build_write_high_voltage_protection,
            parser=commands.parse_write_high_voltage_protection_response,
            enabled=enabled,
        )

    async def async_get_low_voltage_protection(
        self,
    ) -> bool | None:
        """Return the low-voltage-protection state."""

        commands = cast(
            LowVoltageProtectionCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.LOW_VOLTAGE_PROTECTION,
            builder=commands.build_read_low_voltage_protection,
            parser=commands.parse_low_voltage_protection_response,
        )

    async def async_set_low_voltage_protection(
        self,
        enabled: bool,
    ) -> bool:
        """Set the low-voltage-protection state."""

        commands = cast(
            LowVoltageProtectionCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.LOW_VOLTAGE_PROTECTION,
            builder=commands.build_write_low_voltage_protection,
            parser=commands.parse_write_low_voltage_protection_response,
            enabled=enabled,
        )

    async def async_get_high_power_protection(
        self,
    ) -> bool | None:
        """Return the high-power-protection state."""

        commands = cast(
            HighPowerProtectionCommands,
            self._device.commands,
        )

        return await self._async_get_switch_value(
            capability=SwitchCapability.HIGH_POWER_PROTECTION,
            builder=commands.build_read_high_power_protection,
            parser=commands.parse_high_power_protection_response,
        )

    async def async_set_high_power_protection(
        self,
        enabled: bool,
    ) -> bool:
        """Set the high-power-protection state."""

        commands = cast(
            HighPowerProtectionCommands,
            self._device.commands,
        )

        return await self._async_set_switch_value(
            capability=SwitchCapability.HIGH_POWER_PROTECTION,
            builder=commands.build_write_high_power_protection,
            parser=commands.parse_write_high_power_protection_response,
            enabled=enabled,
        )
