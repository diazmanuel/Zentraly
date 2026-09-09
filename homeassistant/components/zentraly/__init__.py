"""The Zentraly integration."""

from datetime import datetime
import logging

from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .api import SCAN_INTERVAL, ZentralyApi
from .const import DOMAIN
from .devices import get_device_commands
from .devices.device import DeviceModel, get_device_model, get_device_platforms
from .exceptions import ZentralyAuthenticationError, ZentralyConnectionError
from .models import ZentralyConfigEntry, ZentralyData, ZentralyDevice

_LOGGER = logging.getLogger(__name__)


def create_device(
    api: ZentralyApi,
    device_id: str,
    mac: str,
    *,
    via_device_id: str | None = None,
) -> ZentralyDevice:
    """Create a runtime representation of a Zentraly device."""

    device_model = get_device_model(device_id)

    if device_model is DeviceModel.UNKNOWN:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="unsupported_model",
            translation_placeholders={"device_id": device_id},
        )

    commands = get_device_commands(device_model)

    return ZentralyDevice(
        api=api,
        device_id=device_id,
        mac=mac,
        device_model=device_model,
        commands=commands,
        via_device_id=via_device_id,
    )


def get_runtime_platforms(
    data: ZentralyData,
) -> list[Platform]:
    """Return all platforms required by a Zentraly config entry."""

    platforms = set(
        get_device_platforms(
            data.device.device_id,
        )
    )

    for child in data.children.values():
        platforms.update(
            get_device_platforms(
                child.device_id,
            )
        )

    return sorted(
        platforms,
        key=lambda platform: platform.value,
    )


def _supports_device_info_polling(
    device: ZentralyDevice,
) -> bool:
    """Return whether the device supports device-information polling."""

    firmware_builder = getattr(
        device.commands,
        "build_read_firmware_version",
        None,
    )
    firmware_parser = getattr(
        device.commands,
        "parse_firmware_version_response",
        None,
    )
    hardware_builder = getattr(
        device.commands,
        "build_read_hardware_version",
        None,
    )
    hardware_parser = getattr(
        device.commands,
        "parse_hardware_version_response",
        None,
    )

    return (
        callable(firmware_builder)
        and callable(firmware_parser)
        and callable(hardware_builder)
        and callable(hardware_parser)
    )


async def _async_read_device_info_value(
    device: ZentralyDevice,
    *,
    builder_name: str,
    parser_name: str,
) -> str | None:
    """Read one device-information value."""

    builder = getattr(
        device.commands,
        builder_name,
        None,
    )
    parser = getattr(
        device.commands,
        parser_name,
        None,
    )

    if not callable(builder) or not callable(parser):
        return None

    result = await device.async_execute_command(
        lambda rid: builder(
            rid,
            device.mac,
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

    if not isinstance(value, str):
        return None

    return value


async def _async_refresh_device_info(
    device: ZentralyDevice,
    device_registry: dr.DeviceRegistry,
    registry_device_id: str,
) -> None:
    """Refresh firmware and hardware information for a Zentraly device."""

    if not device.connected:
        return

    firmware_version = await _async_read_device_info_value(
        device,
        builder_name="build_read_firmware_version",
        parser_name="parse_firmware_version_response",
    )

    hardware_version = await _async_read_device_info_value(
        device,
        builder_name="build_read_hardware_version",
        parser_name="parse_hardware_version_response",
    )

    changed = False

    if firmware_version is not None and firmware_version != device.firmware_version:
        device.firmware_version = firmware_version
        changed = True

    if hardware_version is not None and hardware_version != device.hardware_version:
        device.hardware_version = hardware_version
        changed = True

    if not changed:
        return

    device_registry.async_update_device(
        registry_device_id,
        sw_version=device.firmware_version,
        hw_version=device.hardware_version,
    )

    _LOGGER.debug(
        "Updated Zentraly device information: device_id=%s firmware=%s hardware=%s",
        device.device_id,
        device.firmware_version,
        device.hardware_version,
    )


def _register_device_info_polling(
    hass: HomeAssistant,
    entry: ZentralyConfigEntry,
    device: ZentralyDevice,
    device_registry: dr.DeviceRegistry,
    registry_device_id: str,
) -> None:
    """Register periodic device-information polling when supported."""

    if not _supports_device_info_polling(device):
        return

    async def _async_periodic_device_info_refresh(
        now: datetime,
    ) -> None:
        """Periodically refresh Zentraly device information."""

        await _async_refresh_device_info(
            device,
            device_registry,
            registry_device_id,
        )

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            _async_periodic_device_info_refresh,
            SCAN_INTERVAL,
        )
    )


async def _async_reload_entry(
    hass: HomeAssistant,
    entry: ZentralyConfigEntry,
) -> None:
    """Reload Zentraly when the config entry or its subentries change."""

    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZentralyConfigEntry,
) -> bool:
    """Set up Zentraly from a config entry."""

    device_id = entry.data[CONF_DEVICE_ID]

    api = ZentralyApi(
        mac=entry.data[CONF_MAC],
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        password=entry.data[CONF_PASSWORD],
        device_id=device_id,
    )

    try:
        mac = await api.async_validate_password()

    except ZentralyAuthenticationError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="authentication_failed",
            translation_placeholders={"device_id": api.device_id},
        ) from err

    except ZentralyConnectionError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="setup_cannot_connect",
            translation_placeholders={"device_id": api.device_id},
        ) from err

    if mac != entry.data[CONF_MAC]:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="unexpected_device",
            translation_placeholders={"host": api.host},
        )

    device = create_device(
        api=api,
        device_id=device_id,
        mac=entry.data[CONF_MAC],
    )

    #
    # Register the parent device before creating child runtime devices.
    #
    # Children use the Home Assistant Device Registry ID of this device
    # as their via_device_id.
    #

    device_registry = dr.async_get(hass)

    parent_device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **device.device_info,
    )

    children: dict[str, ZentralyDevice] = {}
    child_registry_ids: dict[str, str] = {}

    for subentry_id, subentry in entry.subentries.items():
        child_device_id = subentry.data.get(CONF_DEVICE_ID)
        child_mac = subentry.data.get(CONF_MAC)

        if not isinstance(child_device_id, str):
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="missing_device_id",
                translation_placeholders={"subentry_id": subentry_id},
            )

        if not isinstance(child_mac, str):
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="missing_mac",
                translation_placeholders={"subentry_id": subentry_id},
            )

        child = create_device(
            api=api,
            device_id=child_device_id,
            mac=child_mac,
            via_device_id=parent_device_entry.id,
        )

        children[subentry_id] = child

        child_device_entry = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry_id,
            **child.device_info,
        )

        child_registry_ids[subentry_id] = child_device_entry.id

    runtime_data = ZentralyData(
        api=api,
        device=device,
        children=children,
    )

    platforms = get_runtime_platforms(runtime_data)

    if not platforms:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="no_platforms",
            translation_placeholders={"device_id": device.device_id},
        )

    await api.async_connect()

    entry.runtime_data = runtime_data

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    _register_device_info_polling(
        hass,
        entry,
        device,
        device_registry,
        parent_device_entry.id,
    )

    for subentry_id, child in children.items():
        _register_device_info_polling(
            hass,
            entry,
            child,
            device_registry,
            child_registry_ids[subentry_id],
        )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        platforms,
    )

    _LOGGER.info(
        "Zentraly device created in Home Assistant: "
        "device_id=%s mac=%s ip=%s children=%s",
        device.device_id,
        device.mac,
        api.host,
        len(children),
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ZentralyConfigEntry,
) -> bool:
    """Unload a Zentraly config entry."""

    platforms = get_runtime_platforms(entry.runtime_data)

    unloaded = await hass.config_entries.async_unload_platforms(
        entry,
        platforms,
    )

    if unloaded:
        await entry.runtime_data.api.async_disconnect()

    return unloaded
