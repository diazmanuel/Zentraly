"""High-level API for Zentraly number devices."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from ...exceptions import ZentralyInvalidResponseError, ZentralyValidationError
from ..select.capabilities import SelectCapability
from ..select.command_protocols import OperationModeCommands
from ..switch.capabilities import SwitchCapability
from ..switch.command_protocols import PowerCommands
from ..types import SelectOperationMode
from .capabilities import NumberCapability
from .command_protocols import (
    HighPowerLimitCommands,
    HighVoltageLimitCommands,
    LowVoltageLimitCommands,
    TimerCommands,
)

if TYPE_CHECKING:
    from ...models import ZentralyDevice

type NumberStateUpdate = dict[NumberCapability, Any]
type NumberStateListener = Callable[[NumberStateUpdate], None]

type NumberRange = tuple[float, float, float]
type NumberReadBuilder = Callable[[int, str], dict[str, Any]]
type NumberReadParser = Callable[[dict[str, Any], int], float]
type NumberWriteBuilder = Callable[[int, str, float], dict[str, Any]]
type NumberWriteParser = Callable[[dict[str, Any], int], None]


class ZentralyNumberApi:
    """High-level API for Zentraly number devices."""

    def __init__(self, device: ZentralyDevice) -> None:
        """Initialize the number API."""

        self._device = device

        self._state_listeners: set[NumberStateListener] = set()
        self._remove_report_listener: Callable[[], None] | None = None

    @property
    def device(self) -> ZentralyDevice:
        """Return the underlying Zentraly device."""

        return self._device

    def supports(
        self,
        capability: NumberCapability,
    ) -> bool:
        """Return whether the device supports a capability."""

        return self._device.supports(capability)

    def get_range(
        self,
        capability: NumberCapability,
    ) -> NumberRange | None:
        """Return the model-specific range for a number capability."""

        ranges = getattr(
            self._device.commands,
            "number_ranges",
            None,
        )

        if not isinstance(ranges, dict):
            return None

        number_range = ranges.get(capability)

        if (
            not isinstance(number_range, tuple)
            or len(number_range) != 3
            or not all(isinstance(value, int | float) for value in number_range)
        ):
            return None

        minimum, maximum, step = number_range

        return (
            float(minimum),
            float(maximum),
            float(step),
        )

    def add_state_listener(
        self,
        listener: NumberStateListener,
    ) -> Callable[[], None]:
        """Register a number state update listener."""

        self._state_listeners.add(listener)

        if self._remove_report_listener is None:
            self._remove_report_listener = self._device.add_report_listener(
                self._handle_report
            )

        def remove_listener() -> None:
            """Remove the number state listener."""

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
        """Parse and dispatch number updates from a device report."""

        parser = getattr(
            self._device.commands,
            "parse_report_entry",
            None,
        )

        if not callable(parser):
            return

        updates: NumberStateUpdate = {}

        for entry in report_data:
            try:
                result = parser(entry)

            except TypeError, ValueError:
                continue

            if result is None:
                continue

            capability, value = result

            if not isinstance(capability, NumberCapability):
                continue

            if not self.supports(capability):
                continue

            if not isinstance(value, int | float):
                continue

            updates[capability] = float(value)

        if not updates:
            return

        for listener in tuple(self._state_listeners):
            listener(updates)

    async def _async_get_number_value(
        self,
        *,
        capability: NumberCapability,
        builder: NumberReadBuilder,
        parser: NumberReadParser,
    ) -> float | None:
        """Read a number capability from the device."""

        if not self.supports(capability):
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

        if not isinstance(value, int | float):
            return None

        return float(value)

    async def _async_set_number_value(
        self,
        *,
        capability: NumberCapability,
        builder: NumberWriteBuilder,
        parser: NumberWriteParser,
        value: float,
    ) -> bool:
        """Write a number capability to the device."""

        if not self.supports(capability):
            raise ZentralyValidationError("Unsupported action")

        result = await self._device.async_execute_action_command(
            lambda rid: builder(
                rid,
                self._device.mac,
                value,
            )
        )

        rid, response = result

        try:
            parser(
                response,
                rid,
            )

        except (TypeError, ValueError) as err:
            raise ZentralyInvalidResponseError("Invalid action response") from err

        return True

    async def async_get_timer(
        self,
    ) -> float | None:
        """Return the current timer duration in minutes."""

        commands = cast(
            TimerCommands,
            self._device.commands,
        )

        return await self._async_get_number_value(
            capability=NumberCapability.TIMER,
            builder=commands.build_read_timer,
            parser=commands.parse_timer_response,
        )

    async def async_set_timer(
        self,
        value: float,
    ) -> bool:
        """Set the timer and automatically enter timer mode."""

        if not self.supports(NumberCapability.TIMER):
            raise ZentralyValidationError("Unsupported action")

        if not self._device.supports(SwitchCapability.POWER):
            raise ZentralyValidationError("Unsupported action")

        if not self._device.supports(SelectCapability.OPERATION_MODE):
            raise ZentralyValidationError("Unsupported action")

        power_commands = cast(
            PowerCommands,
            self._device.commands,
        )

        timer_commands = cast(
            TimerCommands,
            self._device.commands,
        )

        operation_mode_commands = cast(
            OperationModeCommands,
            self._device.commands,
        )

        power_result = await self._device.async_execute_action_command(
            lambda rid: power_commands.build_read_power_state(
                rid,
                self._device.mac,
            )
        )

        power_rid, power_response = power_result

        try:
            power_on = power_commands.parse_power_state_response(
                power_response,
                power_rid,
            )

        except (TypeError, ValueError) as err:
            raise ZentralyInvalidResponseError("Invalid action response") from err

        if not isinstance(power_on, bool):
            raise ZentralyInvalidResponseError("Invalid power state")

        timer_result = await self._device.async_execute_action_command(
            lambda rid: timer_commands.build_write_timer(
                rid,
                self._device.mac,
                value,
                power_on,
            )
        )

        timer_rid, timer_response = timer_result

        try:
            timer_commands.parse_write_timer_response(
                timer_response,
                timer_rid,
            )

        except (TypeError, ValueError) as err:
            raise ZentralyInvalidResponseError("Invalid action response") from err

        mode_result = await self._device.async_execute_action_command(
            lambda rid: operation_mode_commands.build_write_operation_mode(
                rid,
                self._device.mac,
                SelectOperationMode.TIMER,
            )
        )

        mode_rid, mode_response = mode_result

        try:
            operation_mode_commands.parse_write_operation_mode_response(
                mode_response,
                mode_rid,
            )

        except (TypeError, ValueError) as err:
            raise ZentralyInvalidResponseError("Invalid action response") from err

        return True

    async def async_get_high_voltage_limit(
        self,
    ) -> float | None:
        """Return the high-voltage limit."""

        commands = cast(
            HighVoltageLimitCommands,
            self._device.commands,
        )

        return await self._async_get_number_value(
            capability=NumberCapability.HIGH_VOLTAGE_LIMIT,
            builder=commands.build_read_high_voltage_limit,
            parser=commands.parse_high_voltage_limit_response,
        )

    async def async_set_high_voltage_limit(
        self,
        value: float,
    ) -> bool:
        """Set the high-voltage limit."""

        commands = cast(
            HighVoltageLimitCommands,
            self._device.commands,
        )

        return await self._async_set_number_value(
            capability=NumberCapability.HIGH_VOLTAGE_LIMIT,
            builder=commands.build_write_high_voltage_limit,
            parser=commands.parse_write_high_voltage_limit_response,
            value=value,
        )

    async def async_get_low_voltage_limit(
        self,
    ) -> float | None:
        """Return the low-voltage limit."""

        commands = cast(
            LowVoltageLimitCommands,
            self._device.commands,
        )

        return await self._async_get_number_value(
            capability=NumberCapability.LOW_VOLTAGE_LIMIT,
            builder=commands.build_read_low_voltage_limit,
            parser=commands.parse_low_voltage_limit_response,
        )

    async def async_set_low_voltage_limit(
        self,
        value: float,
    ) -> bool:
        """Set the low-voltage limit."""

        commands = cast(
            LowVoltageLimitCommands,
            self._device.commands,
        )

        return await self._async_set_number_value(
            capability=NumberCapability.LOW_VOLTAGE_LIMIT,
            builder=commands.build_write_low_voltage_limit,
            parser=commands.parse_write_low_voltage_limit_response,
            value=value,
        )

    async def async_get_high_power_limit(
        self,
    ) -> float | None:
        """Return the high-power limit."""

        commands = cast(
            HighPowerLimitCommands,
            self._device.commands,
        )

        return await self._async_get_number_value(
            capability=NumberCapability.HIGH_POWER_LIMIT,
            builder=commands.build_read_high_power_limit,
            parser=commands.parse_high_power_limit_response,
        )

    async def async_set_high_power_limit(
        self,
        value: float,
    ) -> bool:
        """Set the high-power limit."""

        commands = cast(
            HighPowerLimitCommands,
            self._device.commands,
        )

        return await self._async_set_number_value(
            capability=NumberCapability.HIGH_POWER_LIMIT,
            builder=commands.build_write_high_power_limit,
            parser=commands.parse_write_high_power_limit_response,
            value=value,
        )
