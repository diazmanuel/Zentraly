"""Select platform for Zentraly."""

from datetime import datetime
from typing import Any, override

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .api import SCAN_INTERVAL
from .device_classes.select.api import ZentralySelectApi
from .device_classes.select.capabilities import SelectCapability
from .device_classes.types import SelectOperationMode
from .models import ZentralyConfigEntry, ZentralyDevice


def _create_select_entities(
    device: ZentralyDevice,
) -> list[ZentralySelect]:
    """Create select entities supported by a Zentraly device."""

    select_api = ZentralySelectApi(device)

    return [
        ZentralySelect(
            device=device,
            select_api=select_api,
            capability=capability,
        )
        for capability in SelectCapability
        if select_api.supports(capability)
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZentralyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zentraly select entities."""

    parent_entities = _create_select_entities(
        entry.runtime_data.device,
    )

    if parent_entities:
        async_add_entities(
            parent_entities,
            True,
        )

    for subentry_id, child in entry.runtime_data.children.items():
        child_entities = _create_select_entities(
            child,
        )

        if not child_entities:
            continue

        async_add_entities(
            child_entities,
            True,
            config_subentry_id=subentry_id,
        )


class ZentralySelect(SelectEntity):
    """Representation of a Zentraly select."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        *,
        device: ZentralyDevice,
        select_api: ZentralySelectApi,
        capability: SelectCapability,
    ) -> None:
        """Initialize the Zentraly select."""

        self._device = device
        self._select_api = select_api
        self._capability = capability

        self._attr_unique_id = f"{device.device_id}_{capability.value}"
        self._attr_translation_key = capability.value

        self._attr_options = [
            option.value for option in select_api.get_options(capability)
        ]

    @override
    async def async_added_to_hass(self) -> None:
        """Register Zentraly listeners and periodic state refresh."""

        await super().async_added_to_hass()

        self.async_on_remove(
            self._device.add_connection_state_listener(self._handle_connection_state)
        )

        self.async_on_remove(
            self._select_api.add_state_listener(self._handle_state_update)
        )

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
        """Refresh select state periodically."""

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

        self.async_schedule_update_ha_state(force_refresh=True)

    def _handle_state_update(
        self,
        updates: dict[SelectCapability, Any],
    ) -> None:
        """Handle select updates received from Zentraly reports."""

        if self._capability not in updates:
            return

        value = updates[self._capability]

        if not isinstance(value, SelectOperationMode):
            return

        option = value.value

        if option not in self._attr_options:
            self._attr_current_option = None
            self.async_write_ha_state()
            return

        self._attr_current_option = option
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update select state from the Zentraly device."""

        self._attr_available = self._device.connected

        if not self._device.connected:
            return

        if self._capability is not SelectCapability.OPERATION_MODE:
            return

        value = await self._select_api.async_get_operation_mode()

        if value is None:
            return

        option = value.value

        if option not in self._attr_options:
            self._attr_current_option = None
            return

        self._attr_current_option = option

    @override
    async def async_select_option(
        self,
        option: str,
    ) -> None:
        """Select a Zentraly option."""

        if not self._device.connected:
            return

        try:
            mode = SelectOperationMode(option)

        except ValueError:
            return

        if self._capability is not SelectCapability.OPERATION_MODE:
            return

        success = await self._select_api.async_set_operation_mode(mode)

        if not success:
            return

        self._attr_current_option = mode.value
        self.async_write_ha_state()

    @property
    @override
    def device_info(self) -> DeviceInfo:
        """Return device information."""

        return self._device.device_info
