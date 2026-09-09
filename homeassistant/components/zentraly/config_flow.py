"""Config flow for the Zentraly integration."""

from collections.abc import Mapping
import logging
from typing import Any, override

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow as HAConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
)
from homeassistant.core import callback
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import ZentralyApi
from .const import DOMAIN
from .devices.device import (
    DeviceModel,
    get_device_model,
    get_max_child_devices,
    is_allowed_child_device,
    supports_child_devices,
    supports_zeroconf_setup,
)
from .exceptions import ZentralyAuthenticationError, ZentralyConnectionError

_LOGGER = logging.getLogger(__name__)

SUBENTRY_TYPE_DEVICE = "device"

PASSWORD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): str,
    }
)

CHILD_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_MAC): str,
    }
)


def _device_id_is_configured_as_subentry(
    config_entries: list[ConfigEntry],
    device_id: str,
) -> bool:
    """Return whether a device ID is configured as a Zentraly subentry."""

    for entry in config_entries:
        for subentry in entry.subentries.values():
            if subentry.unique_id == device_id:
                return True

            if subentry.data.get(CONF_DEVICE_ID) == device_id:
                return True

    return False


def _device_id_is_configured(
    config_entries: list[ConfigEntry],
    device_id: str,
) -> bool:
    """Return whether a device ID is already configured in Zentraly."""

    for entry in config_entries:
        if entry.unique_id == device_id:
            return True

        if entry.data.get(CONF_DEVICE_ID) == device_id:
            return True

        for subentry in entry.subentries.values():
            if subentry.unique_id == device_id:
                return True

            if subentry.data.get(CONF_DEVICE_ID) == device_id:
                return True

    return False


def _child_limit_reached(
    entry: ConfigEntry,
    parent_device_id: str,
) -> bool:
    """Return whether a parent reached its child-device limit."""

    max_children = get_max_child_devices(parent_device_id)

    child_count = len(
        entry.get_subentries_of_type(
            SUBENTRY_TYPE_DEVICE,
        )
    )

    return child_count >= max_children


class ZentralyConfigFlow(HAConfigFlow, domain=DOMAIN):
    """Handle a Zentraly config flow."""

    def __init__(self) -> None:
        """Initialize the config flow."""

        self.data: dict[str, Any] = {}

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls,
        config_entry: ConfigEntry,
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentries supported by this config entry."""

        device_id = config_entry.data.get(CONF_DEVICE_ID)

        if not isinstance(device_id, str):
            return {}

        if not supports_child_devices(device_id):
            return {}

        if _child_limit_reached(config_entry, device_id):
            return {}

        return {
            SUBENTRY_TYPE_DEVICE: ZentralyDeviceSubentryFlow,
        }

    @override
    async def async_step_zeroconf(
        self,
        discovery_info: ZeroconfServiceInfo,
    ) -> ConfigFlowResult:
        """Handle Zeroconf discovery."""

        device_id = discovery_info.name.split(".")[0]

        if not supports_zeroconf_setup(device_id):
            return self.async_abort(reason="unsupported_device")

        entries = self.hass.config_entries.async_entries(DOMAIN)

        if _device_id_is_configured_as_subentry(
            entries,
            device_id,
        ):
            return self.async_abort(reason="already_configured")

        self.data[CONF_HOST] = discovery_info.host
        self.data[CONF_PORT] = discovery_info.port
        self.data[CONF_DEVICE_ID] = device_id

        self.context.update(
            {
                "title_placeholders": {
                    "name": device_id,
                }
            }
        )

        _LOGGER.info(
            "Zentraly device discovered: %s at %s:%s",
            device_id,
            self.data[CONF_HOST],
            self.data[CONF_PORT],
        )

        await self.async_set_unique_id(device_id)

        self._abort_if_unique_id_configured(
            updates={
                CONF_HOST: discovery_info.host,
                CONF_PORT: discovery_info.port,
            },
            reload_on_update=False,
        )

        return await self.async_step_auth()

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Request a replacement password for the existing device."""
        entry = self._get_reauth_entry()
        self.data = dict(entry.data)
        self.context["title_placeholders"] = {"name": entry.data[CONF_DEVICE_ID]}
        return await self.async_step_auth()

    async def async_step_auth(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle password authentication."""

        errors: dict[str, str] = {}

        if user_input is not None:
            password = user_input[CONF_PASSWORD]

            api = ZentralyApi(
                host=self.data[CONF_HOST],
                port=self.data[CONF_PORT],
                password=password,
                device_id=self.data[CONF_DEVICE_ID],
            )

            try:
                mac = await api.async_validate_password()

            except ZentralyAuthenticationError:
                errors["base"] = "invalid_auth"

            except ZentralyConnectionError:
                errors["base"] = "cannot_connect"

            else:
                if self.source == SOURCE_REAUTH:
                    entry = self._get_reauth_entry()
                    if mac.lower() != entry.data[CONF_MAC].lower():
                        return self.async_abort(reason="wrong_device")

                    reload_by_listener = (
                        bool(entry.update_listeners)
                        and password != entry.data[CONF_PASSWORD]
                    )
                    result = self.async_update_and_abort(
                        entry, data_updates={CONF_PASSWORD: password}
                    )
                    if not reload_by_listener:
                        self.hass.config_entries.async_schedule_reload(entry.entry_id)
                    return result

                self.data[CONF_PASSWORD] = password
                self.data[CONF_MAC] = mac

                _LOGGER.info(
                    "Zentraly device validated: device_id=%s mac=%s ip=%s",
                    self.data[CONF_DEVICE_ID],
                    mac,
                    self.data[CONF_HOST],
                )

                return self.async_create_entry(
                    title=self.data[CONF_DEVICE_ID],
                    data=self.data,
                )

        return self.async_show_form(
            step_id="auth",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders=self.context["title_placeholders"],
        )

    @override
    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle manual setup."""

        return self.async_abort(reason="zeroconf_only")


class ZentralyDeviceSubentryFlow(ConfigSubentryFlow):
    """Handle Zentraly child-device subentries."""

    async def async_step_device(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        """Handle the child-device subentry entry point."""

        return await self.async_step_user(user_input)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        """Add a Zentraly child device."""

        entry = self._get_entry()

        if entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        parent_device_id = entry.data.get(CONF_DEVICE_ID)

        if not isinstance(parent_device_id, str):
            return self.async_abort(reason="unsupported_parent")

        if not supports_child_devices(parent_device_id):
            return self.async_abort(reason="unsupported_parent")

        if _child_limit_reached(entry, parent_device_id):
            return self.async_abort(reason="max_children")

        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = str(user_input[CONF_DEVICE_ID]).strip().upper()

            try:
                mac = self._normalize_mac(str(user_input[CONF_MAC]))

            except vol.Invalid:
                errors["base"] = "invalid_mac"

            else:
                device_model = get_device_model(device_id)

                if device_model is DeviceModel.UNKNOWN:
                    errors["base"] = "unsupported_device"

                elif not is_allowed_child_device(
                    parent_device_id,
                    device_id,
                ):
                    errors["base"] = "unsupported_child"

                elif _device_id_is_configured(
                    self.hass.config_entries.async_entries(DOMAIN),
                    device_id,
                ):
                    errors["base"] = "already_configured"

                else:
                    try:
                        await entry.runtime_data.api.async_validate_child_device(
                            device_id,
                            mac,
                        )

                    except ZentralyConnectionError:
                        errors["base"] = "cannot_connect"

                    except TypeError, ValueError:
                        errors["base"] = "invalid_device"

                    else:
                        _LOGGER.info(
                            "Zentraly child device validated: "
                            "parent=%s device_id=%s mac=%s",
                            parent_device_id,
                            device_id,
                            mac,
                        )

                        return self.async_create_entry(
                            title=device_id,
                            unique_id=device_id,
                            data={
                                CONF_DEVICE_ID: device_id,
                                CONF_MAC: mac,
                            },
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=CHILD_DEVICE_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def _normalize_mac(
        mac: str,
    ) -> str:
        """Normalize and validate a Zentraly MAC address."""

        normalized_mac = mac.strip().lower().replace(":", "").replace("-", "")

        if len(normalized_mac) != 12:
            raise vol.Invalid(
                "Zentraly MAC address must contain 12 hexadecimal characters"
            )

        if any(character not in "0123456789abcdef" for character in normalized_mac):
            raise vol.Invalid(
                "Zentraly MAC address must contain only hexadecimal characters"
            )

        return normalized_mac
