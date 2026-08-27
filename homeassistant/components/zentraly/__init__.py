"""The Zentraly integration."""

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

from .api import ZentralyApi, ZentralyAuthenticationError, ZentralyConnectionError
from .devices import get_device_commands
from .devices.device import DeviceModel, get_device_model, get_device_platforms
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
        raise ConfigEntryError(f"Unsupported Zentraly device model: {device_id}")

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
            f"Authentication failed for Zentraly device {api.device_id}"
        ) from err

    except ZentralyConnectionError as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to Zentraly device {api.device_id}"
        ) from err

    if mac != entry.data[CONF_MAC]:
        raise ConfigEntryNotReady(f"Unexpected Zentraly device at {api.host}")

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

    for subentry_id, subentry in entry.subentries.items():
        child_device_id = subentry.data.get(CONF_DEVICE_ID)
        child_mac = subentry.data.get(CONF_MAC)

        if not isinstance(child_device_id, str):
            raise ConfigEntryError(
                f"Missing device ID for Zentraly subentry {subentry_id}"
            )

        if not isinstance(child_mac, str):
            raise ConfigEntryError(
                f"Missing MAC address for Zentraly subentry {subentry_id}"
            )

        children[subentry_id] = create_device(
            api=api,
            device_id=child_device_id,
            mac=child_mac,
            via_device_id=parent_device_entry.id,
        )

    runtime_data = ZentralyData(
        api=api,
        device=device,
        children=children,
    )

    platforms = get_runtime_platforms(runtime_data)

    if not platforms:
        raise ConfigEntryError(
            "No supported Home Assistant platforms for "
            f"Zentraly device {device.device_id}"
        )

    await api.async_connect()

    entry.runtime_data = runtime_data

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

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
