"""Sensor platform for Zentraly."""

from datetime import datetime
from typing import Any, override

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .api import SCAN_INTERVAL
from .device_classes.sensor.api import ZentralySensorApi
from .device_classes.sensor.capabilities import SensorCapability
from .device_classes.sensor.types import SensorOutputType
from .models import ZentralyConfigEntry, ZentralyDevice


def _create_sensor_entities(
    device: ZentralyDevice,
) -> list[ZentralySensor]:
    """Create sensor entities supported by a Zentraly device."""

    sensor_api = ZentralySensorApi(device)
    entities: list[ZentralySensor] = []

    if sensor_api.supports(SensorCapability.ERRORS):
        entities.append(
            ZentralySensor(
                device=device,
                sensor_api=sensor_api,
                capability=SensorCapability.ERRORS,
            )
        )

    if sensor_api.supports(SensorCapability.OUTPUT_TYPE):
        entities.append(
            ZentralySensor(
                device=device,
                sensor_api=sensor_api,
                capability=SensorCapability.OUTPUT_TYPE,
            )
        )

    if sensor_api.supports(SensorCapability.RSSI):
        entities.append(
            ZentralySensor(
                device=device,
                sensor_api=sensor_api,
                capability=SensorCapability.RSSI,
            )
        )

    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZentralyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zentraly sensor entities."""

    parent_entities = _create_sensor_entities(
        entry.runtime_data.device,
    )

    if parent_entities:
        async_add_entities(
            parent_entities,
            True,
        )

    for subentry_id, child in entry.runtime_data.children.items():
        child_entities = _create_sensor_entities(
            child,
        )

        if not child_entities:
            continue

        async_add_entities(
            child_entities,
            True,
            config_subentry_id=subentry_id,
        )


class ZentralySensor(SensorEntity):
    """Representation of a Zentraly sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        *,
        device: ZentralyDevice,
        sensor_api: ZentralySensorApi,
        capability: SensorCapability,
    ) -> None:
        """Initialize the Zentraly sensor."""

        self._device = device
        self._sensor_api = sensor_api
        self._capability = capability

        self._attr_unique_id = f"{device.device_id}_{capability.value}"
        self._attr_translation_key = capability.value

        if capability is SensorCapability.RSSI:
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT

        elif capability is SensorCapability.OUTPUT_TYPE:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = [output_type.value for output_type in SensorOutputType]

    @override
    async def async_added_to_hass(self) -> None:
        """Register Zentraly listeners and periodic state refresh."""

        await super().async_added_to_hass()

        self.async_on_remove(
            self._device.add_connection_state_listener(self._handle_connection_state)
        )

        self.async_on_remove(
            self._sensor_api.add_state_listener(self._handle_state_update)
        )

        if self._capability is not SensorCapability.RSSI:
            self.async_on_remove(
                async_track_time_interval(
                    self.hass,
                    self._async_periodic_refresh,
                    SCAN_INTERVAL,
                )
            )

    async def _async_periodic_refresh(
        self,
        now: datetime,
    ) -> None:
        """Refresh sensor state periodically as a synchronization fallback."""

        await self.async_update()
        self.async_write_ha_state()

    def _handle_connection_state(
        self,
        connected: bool,
    ) -> None:
        """Handle Zentraly connection-state changes."""

        self._attr_available = connected

        if not connected:
            self.async_write_ha_state()
            return

        if self._capability is SensorCapability.RSSI:
            self.async_write_ha_state()
            return

        self.async_schedule_update_ha_state(force_refresh=True)

    def _handle_state_update(
        self,
        updates: dict[SensorCapability, Any],
    ) -> None:
        """Handle sensor state updates received from Zentraly reports."""

        if self._capability not in updates:
            return

        value = updates[self._capability]

        if self._capability is SensorCapability.OUTPUT_TYPE:
            if not isinstance(value, SensorOutputType):
                return

            self._attr_native_value = value.value

        elif self._capability in (
            SensorCapability.ERRORS,
            SensorCapability.RSSI,
        ):
            if not isinstance(value, int):
                return

            self._attr_native_value = value

        else:
            return

        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update sensor state from the Zentraly device."""

        self._attr_available = self._device.connected

        if not self._device.connected:
            return

        if self._capability is SensorCapability.ERRORS:
            errors = await self._sensor_api.async_get_errors()

            if errors is not None:
                self._attr_native_value = errors

            return

        if self._capability is SensorCapability.OUTPUT_TYPE:
            output_type = await self._sensor_api.async_get_output_type()

            if output_type is not None:
                self._attr_native_value = output_type.value

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device information."""

        return self._device.device_info
