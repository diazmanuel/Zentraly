"""High-level API for Zentraly select devices."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from ...exceptions import ZentralyInvalidResponseError, ZentralyValidationError
from ..types import SelectOperationMode
from .capabilities import SelectCapability
from .command_protocols import OperationModeCommands

if TYPE_CHECKING:
    from ...models import ZentralyDevice

type SelectStateUpdate = dict[SelectCapability, Any]
type SelectStateListener = Callable[[SelectStateUpdate], None]


class ZentralySelectApi:
    """High-level API for Zentraly select devices."""

    def __init__(self, device: ZentralyDevice) -> None:
        """Initialize the select API."""

        self._device = device

        self._state_listeners: set[SelectStateListener] = set()
        self._remove_report_listener: Callable[[], None] | None = None

    @property
    def device(self) -> ZentralyDevice:
        """Return the underlying Zentraly device."""

        return self._device

    def supports(
        self,
        capability: SelectCapability,
    ) -> bool:
        """Return whether the device supports a capability."""

        return self._device.supports(capability)

    def get_options(
        self,
        capability: SelectCapability,
    ) -> tuple[SelectOperationMode, ...]:
        """Return all states supported by a select capability."""

        options = getattr(
            self._device.commands,
            "select_options",
            None,
        )

        if not isinstance(options, dict):
            return ()

        capability_options = options.get(capability)

        if not isinstance(capability_options, tuple):
            return ()

        if not all(
            isinstance(option, SelectOperationMode) for option in capability_options
        ):
            return ()

        return capability_options

    def get_writable_options(
        self,
        capability: SelectCapability,
    ) -> tuple[SelectOperationMode, ...]:
        """Return options that may be selected manually."""

        options = getattr(
            self._device.commands,
            "select_writable_options",
            None,
        )

        if not isinstance(options, dict):
            return ()

        capability_options = options.get(capability)

        if not isinstance(capability_options, tuple):
            return ()

        if not all(
            isinstance(option, SelectOperationMode) for option in capability_options
        ):
            return ()

        return capability_options

    def is_option_writable(
        self,
        capability: SelectCapability,
        option: SelectOperationMode,
    ) -> bool:
        """Return whether an option may be selected manually."""

        return option in self.get_writable_options(capability)

    def add_state_listener(
        self,
        listener: SelectStateListener,
    ) -> Callable[[], None]:
        """Register a select state update listener."""

        self._state_listeners.add(listener)

        if self._remove_report_listener is None:
            self._remove_report_listener = self._device.add_report_listener(
                self._handle_report
            )

        def remove_listener() -> None:
            """Remove the select state listener."""

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
        """Parse and dispatch select updates from a device report."""

        parser = getattr(
            self._device.commands,
            "parse_report_entry",
            None,
        )

        if not callable(parser):
            return

        updates: SelectStateUpdate = {}

        for entry in report_data:
            try:
                result = parser(entry)

            except TypeError, ValueError:
                continue

            if result is None:
                continue

            capability, value = result

            if not isinstance(capability, SelectCapability):
                continue

            if not self.supports(capability):
                continue

            if not isinstance(value, SelectOperationMode):
                continue

            updates[capability] = value

        if not updates:
            return

        for listener in tuple(self._state_listeners):
            listener(updates)

    async def async_get_operation_mode(
        self,
    ) -> SelectOperationMode | None:
        """Return the current operation mode."""

        if not self.supports(SelectCapability.OPERATION_MODE):
            return None

        commands = cast(
            OperationModeCommands,
            self._device.commands,
        )

        result = await self._device.async_execute_command(
            lambda rid: commands.build_read_operation_mode(
                rid,
                self._device.mac,
            )
        )

        if result is None:
            return None

        rid, response = result

        try:
            value = commands.parse_operation_mode_response(
                response,
                rid,
            )

        except TypeError, ValueError:
            return None

        if not isinstance(value, SelectOperationMode):
            return None

        return value

    async def async_set_operation_mode(
        self,
        mode: SelectOperationMode,
    ) -> bool:
        """Set a manually selectable operation mode."""

        if not self.supports(SelectCapability.OPERATION_MODE):
            raise ZentralyValidationError("Unsupported action")

        if not self.is_option_writable(
            SelectCapability.OPERATION_MODE,
            mode,
        ):
            raise ZentralyValidationError("Unsupported action")

        commands = cast(
            OperationModeCommands,
            self._device.commands,
        )

        result = await self._device.async_execute_action_command(
            lambda rid: commands.build_write_operation_mode(
                rid,
                self._device.mac,
                mode,
            )
        )

        rid, response = result

        try:
            commands.parse_write_operation_mode_response(
                response,
                rid,
            )

        except (TypeError, ValueError) as err:
            raise ZentralyInvalidResponseError("Invalid action response") from err

        return True
