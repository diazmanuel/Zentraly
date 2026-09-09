"""Number platform for Zentraly."""

from datetime import datetime
import logging
from typing import Any, override

from homeassistant.components.number import NumberEntity
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .actions import translate_action_errors
from .api import SCAN_INTERVAL
from .device_classes.number.api import ZentralyNumberApi
from .device_classes.number.capabilities import NumberCapability
from .exceptions import (
    ZentralyApiError,
    ZentralyConnectionError,
    ZentralyValidationError,
)
from .models import ZentralyConfigEntry, ZentralyDevice

PARALLEL_UPDATES = 0

_TIMER_DEBOUNCE_SECONDS = 3.0
_LOGGER = logging.getLogger(__name__)

_CONFIG_CAPABILITIES = frozenset(
    {
        NumberCapability.TIMER,
        NumberCapability.HIGH_VOLTAGE_LIMIT,
        NumberCapability.LOW_VOLTAGE_LIMIT,
        NumberCapability.HIGH_POWER_LIMIT,
    }
)


def _create_number_entities(
    device: ZentralyDevice,
) -> list[ZentralyNumber]:
    """Create number entities supported by a Zentraly device."""

    number_api = ZentralyNumberApi(device)

    return [
        ZentralyNumber(
            device=device,
            number_api=number_api,
            capability=capability,
        )
        for capability in NumberCapability
        if number_api.supports(capability)
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZentralyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zentraly number entities."""

    parent_entities = _create_number_entities(
        entry.runtime_data.device,
    )

    if parent_entities:
        async_add_entities(
            parent_entities,
            True,
        )

    for subentry_id, child in entry.runtime_data.children.items():
        child_entities = _create_number_entities(
            child,
        )

        if not child_entities:
            continue

        async_add_entities(
            child_entities,
            True,
            config_subentry_id=subentry_id,
        )


class ZentralyNumber(NumberEntity):
    """Representation of a Zentraly number."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        *,
        device: ZentralyDevice,
        number_api: ZentralyNumberApi,
        capability: NumberCapability,
    ) -> None:
        """Initialize the Zentraly number."""

        self._device = device
        self._number_api = number_api
        self._capability = capability

        self._cancel_timer_write: CALLBACK_TYPE | None = None
        self._pending_timer_value: float | None = None
        self._timer_generation = 0

        self._attr_unique_id = f"{device.device_id}_{capability.value}"
        self._attr_translation_key = capability.value

        number_range = number_api.get_range(capability)

        if number_range is not None:
            (
                self._attr_native_min_value,
                self._attr_native_max_value,
                self._attr_native_step,
            ) = number_range

        if capability in _CONFIG_CAPABILITIES:
            self._attr_entity_category = EntityCategory.CONFIG

        if capability is NumberCapability.TIMER:
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES

        elif capability in (
            NumberCapability.HIGH_VOLTAGE_LIMIT,
            NumberCapability.LOW_VOLTAGE_LIMIT,
        ):
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT

        elif capability is NumberCapability.HIGH_POWER_LIMIT:
            self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @override
    async def async_added_to_hass(self) -> None:
        """Register Zentraly listeners and periodic state refresh."""

        await super().async_added_to_hass()

        self.async_on_remove(
            self._device.add_connection_state_listener(self._handle_connection_state)
        )

        self.async_on_remove(
            self._number_api.add_state_listener(self._handle_state_update)
        )

        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_periodic_refresh,
                SCAN_INTERVAL,
            )
        )

        self.async_on_remove(self._cancel_pending_timer_write)

    def _cancel_pending_timer_write(self) -> None:
        """Cancel a pending timer write."""

        self._timer_generation += 1

        if self._cancel_timer_write is not None:
            self._cancel_timer_write()
            self._cancel_timer_write = None

        self._pending_timer_value = None

    async def _async_write_pending_timer(
        self,
        now: datetime,
    ) -> None:
        """Write the timer after the debounce interval."""

        self._cancel_timer_write = None

        value = self._pending_timer_value
        self._pending_timer_value = None

        if value is None:
            return

        if not self._device.connected:
            return

        generation = self._timer_generation
        try:
            success = await self._number_api.async_set_timer(value)
        except ZentralyApiError as err:
            _LOGGER.error("Timer write failed for %s: %s", self.unique_id, err)
            success = False
        else:
            if not success:
                _LOGGER.error("Timer write failed for %s", self.unique_id)

        if generation != self._timer_generation:
            return

        if success:
            self._attr_native_value = value
            self.async_write_ha_state()
            return

        await self.async_update()
        self.async_write_ha_state()

    async def _async_periodic_refresh(
        self,
        now: datetime,
    ) -> None:
        """Refresh number state periodically."""

        if (
            self._capability is NumberCapability.TIMER
            and self._pending_timer_value is not None
        ):
            return

        await self.async_update()
        self.async_write_ha_state()

    def _handle_connection_state(
        self,
        connected: bool,
    ) -> None:
        """Handle Zentraly connection-state changes."""

        self._attr_available = connected

        if not connected:
            if self._capability is NumberCapability.TIMER:
                self._cancel_pending_timer_write()

            self.async_write_ha_state()
            return

        self.async_schedule_update_ha_state(force_refresh=True)

    def _handle_state_update(
        self,
        updates: dict[NumberCapability, Any],
    ) -> None:
        """Handle number state updates received from Zentraly reports."""

        if self._capability not in updates:
            return

        if (
            self._capability is NumberCapability.TIMER
            and self._pending_timer_value is not None
        ):
            return

        value = updates[self._capability]

        if not isinstance(value, int | float):
            return

        self._attr_native_value = float(value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update number state from the Zentraly device."""

        self._attr_available = self._device.connected

        if not self._device.connected:
            return

        if (
            self._capability is NumberCapability.TIMER
            and self._pending_timer_value is not None
        ):
            return

        value: float | None

        if self._capability is NumberCapability.TIMER:
            generation = self._timer_generation
            value = await self._number_api.async_get_timer()

            if generation != self._timer_generation:
                return

        elif self._capability is NumberCapability.HIGH_VOLTAGE_LIMIT:
            value = await self._number_api.async_get_high_voltage_limit()

        elif self._capability is NumberCapability.LOW_VOLTAGE_LIMIT:
            value = await self._number_api.async_get_low_voltage_limit()

        elif self._capability is NumberCapability.HIGH_POWER_LIMIT:
            value = await self._number_api.async_get_high_power_limit()

        else:
            return

        if value is not None:
            self._attr_native_value = value

    @override
    @translate_action_errors
    async def async_set_native_value(
        self,
        value: float,
    ) -> None:
        """Set the Zentraly number value."""

        if not self._device.connected:
            raise ZentralyConnectionError("Device disconnected")

        if self._capability is NumberCapability.TIMER:
            self._cancel_pending_timer_write()

            self._pending_timer_value = value
            self._attr_native_value = value
            self.async_write_ha_state()

            self._cancel_timer_write = async_call_later(
                self.hass,
                _TIMER_DEBOUNCE_SECONDS,
                self._async_write_pending_timer,
            )

            return

        success: bool

        if self._capability is NumberCapability.HIGH_VOLTAGE_LIMIT:
            success = await self._number_api.async_set_high_voltage_limit(value)

        elif self._capability is NumberCapability.LOW_VOLTAGE_LIMIT:
            success = await self._number_api.async_set_low_voltage_limit(value)

        elif self._capability is NumberCapability.HIGH_POWER_LIMIT:
            success = await self._number_api.async_set_high_power_limit(value)

        else:
            raise ZentralyValidationError("Unsupported action")

        if not success:
            raise ZentralyApiError("Action failed")

        self._attr_native_value = value
        self.async_write_ha_state()

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device information."""

        return self._device.device_info
