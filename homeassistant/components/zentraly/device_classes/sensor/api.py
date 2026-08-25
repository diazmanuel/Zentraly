"""High-level API for Zentraly sensor devices."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .capabilities import SensorCapability
from .types import SensorOutputType

if TYPE_CHECKING:
    from ...models import ZentralyDevice

type SensorStateUpdate = dict[SensorCapability, Any]
type SensorStateListener = Callable[[SensorStateUpdate], None]


class ZentralySensorApi:
    """High-level API for Zentraly sensor devices."""

    def __init__(self, device: ZentralyDevice) -> None:
        """Initialize the sensor API."""

        self._device = device

        self._state_listeners: set[SensorStateListener] = set()
        self._remove_report_listener: Callable[[], None] | None = None

    @property
    def device(self) -> ZentralyDevice:
        """Return the underlying Zentraly device."""

        return self._device

    def supports(
        self,
        capability: SensorCapability,
    ) -> bool:
        """Return whether the device supports a capability."""

        return self._device.supports(capability)

    def add_state_listener(
        self,
        listener: SensorStateListener,
    ) -> Callable[[], None]:
        """Register a sensor state update listener."""

        self._state_listeners.add(listener)

        if self._remove_report_listener is None:
            self._remove_report_listener = self._device.add_report_listener(
                self._handle_report
            )

        def remove_listener() -> None:
            """Remove the sensor state update listener."""

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
        """Parse and dispatch sensor state updates from a device report."""

        parser = getattr(
            self._device.commands,
            "parse_report_entry",
            None,
        )

        if not callable(parser):
            return

        updates: SensorStateUpdate = {}

        for entry in report_data:
            try:
                result = parser(entry)

            except TypeError, ValueError:
                continue

            if result is None:
                continue

            capability, value = result

            if not isinstance(capability, SensorCapability):
                continue

            if not self.supports(capability):
                continue

            updates[capability] = value

        if not updates:
            return

        for listener in tuple(self._state_listeners):
            listener(updates)

    async def async_get_errors(self) -> int | None:
        """Return the current device error value."""

        if not self.supports(SensorCapability.ERRORS):
            return None

        builder = getattr(
            self._device.commands,
            "build_read_errors",
            None,
        )
        parser = getattr(
            self._device.commands,
            "parse_errors_response",
            None,
        )

        if not callable(builder) or not callable(parser):
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

        if not isinstance(value, int):
            return None

        return value

    async def async_get_output_type(
        self,
    ) -> SensorOutputType | None:
        """Return the current device output type."""

        if not self.supports(SensorCapability.OUTPUT_TYPE):
            return None

        builder = getattr(
            self._device.commands,
            "build_read_output_type",
            None,
        )
        parser = getattr(
            self._device.commands,
            "parse_output_type_response",
            None,
        )

        if not callable(builder) or not callable(parser):
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

        if not isinstance(value, SensorOutputType):
            return None

        return value
