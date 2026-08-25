"""High-level API for Zentraly binary sensor devices."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .capabilities import BinarySensorCapability

if TYPE_CHECKING:
    from ...models import ZentralyDevice

type BinarySensorStateUpdate = dict[BinarySensorCapability, Any]
type BinarySensorStateListener = Callable[[BinarySensorStateUpdate], None]


class ZentralyBinarySensorApi:
    """High-level API for Zentraly binary sensor devices."""

    def __init__(self, device: ZentralyDevice) -> None:
        """Initialize the binary sensor API."""

        self._device = device

        self._state_listeners: set[BinarySensorStateListener] = set()
        self._remove_report_listener: Callable[[], None] | None = None

    @property
    def device(self) -> ZentralyDevice:
        """Return the underlying Zentraly device."""

        return self._device

    def supports(
        self,
        capability: BinarySensorCapability,
    ) -> bool:
        """Return whether the device supports a capability."""

        return self._device.supports(capability)

    def add_state_listener(
        self,
        listener: BinarySensorStateListener,
    ) -> Callable[[], None]:
        """Register a binary sensor state update listener."""

        self._state_listeners.add(listener)

        if self._remove_report_listener is None:
            self._remove_report_listener = self._device.add_report_listener(
                self._handle_report
            )

        def remove_listener() -> None:
            """Remove the binary sensor state update listener."""

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
        """Parse and dispatch binary sensor updates from a device report."""

        parser = getattr(
            self._device.commands,
            "parse_report_entry",
            None,
        )

        if not callable(parser):
            return

        updates: BinarySensorStateUpdate = {}

        for entry in report_data:
            try:
                result = parser(entry)

            except TypeError, ValueError:
                continue

            if result is None:
                continue

            capability, value = result

            if not isinstance(capability, BinarySensorCapability):
                continue

            if not self.supports(capability):
                continue

            updates[capability] = value

        if not updates:
            return

        for listener in tuple(self._state_listeners):
            listener(updates)

    async def async_get_on_off(self) -> bool | None:
        """Return the current on/off state."""

        if not self.supports(BinarySensorCapability.ON_OFF):
            return None

        builder = getattr(
            self._device.commands,
            "build_read_on_off",
            None,
        )
        parser = getattr(
            self._device.commands,
            "parse_on_off_response",
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

        if not isinstance(value, bool):
            return None

        return value

    async def async_get_forced_mode(self) -> bool | None:
        """Return the current forced-mode state."""

        if not self.supports(BinarySensorCapability.FORCED_MODE):
            return None

        builder = getattr(
            self._device.commands,
            "build_read_forced_mode",
            None,
        )
        parser = getattr(
            self._device.commands,
            "parse_forced_mode_response",
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

        if not isinstance(value, bool):
            return None

        return value
