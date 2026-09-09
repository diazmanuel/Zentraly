"""Tests for the Zentraly integration setup."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.zentraly import create_device
from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.const import DOMAIN
from homeassistant.components.zentraly.devices.device import (
    DeviceModel,
    get_device_platforms,
)
from homeassistant.components.zentraly.exceptions import (
    ZentralyAuthenticationError,
    ZentralyConnectionError,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr

from tests.common import MockConfigEntry

PARENT_DEVICE_ID = "ZTTIN0100000631"
CHILD_DEVICE_ID = "ZTBIN0100000021"
ZTEIM_DEVICE_ID = "ZTEIM0100000001"

HOST = "192.168.1.42"
PORT = 80

PARENT_MAC = "dcda0c58c8d8"
CHILD_MAC = "1020ba12316c"
ZTEIM_MAC = "aabbccddeeff"

PASSWORD = "test-password"

SUBENTRY_TYPE_DEVICE = "device"


@pytest.mark.parametrize(
    ("error", "expected", "key"),
    [
        pytest.param(
            ZentralyAuthenticationError,
            ConfigEntryState.SETUP_ERROR,
            "authentication_failed",
            id="authentication",
        ),
        pytest.param(
            ZentralyConnectionError,
            ConfigEntryState.SETUP_RETRY,
            "setup_cannot_connect",
            id="connection",
        ),
    ],
)
async def test_translated_setup_error(
    hass: HomeAssistant,
    error: type[Exception],
    expected: ConfigEntryState,
    key: str,
) -> None:
    """Setup failures expose translated messages with the device identifier."""
    entry = _parent_entry()
    entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            side_effect=error,
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is expected
    assert entry.error_reason_translation_key == key
    assert entry.error_reason_translation_placeholders == {
        "device_id": PARENT_DEVICE_ID
    }


def test_translated_unsupported_model() -> None:
    """Unsupported models expose a translation key instead of hardcoded UI text."""
    api = ZentralyApi(HOST, PORT, PASSWORD, "UNKNOWN")
    with pytest.raises(ConfigEntryError) as exc:
        create_device(api, "UNKNOWN", PARENT_MAC)
    assert exc.value.translation_key == "unsupported_model"
    assert exc.value.translation_placeholders == {"device_id": "UNKNOWN"}


@pytest.mark.parametrize(
    ("data", "key"),
    [
        pytest.param({CONF_MAC: CHILD_MAC}, "missing_device_id", id="id"),
        pytest.param({CONF_DEVICE_ID: CHILD_DEVICE_ID}, "missing_mac", id="mac"),
    ],
)
async def test_translated_invalid_subentry(
    hass: HomeAssistant, data: dict[str, str], key: str
) -> None:
    """Invalid stored child data produces a localized initialization error."""
    entry = _parent_entry(
        subentries_data=[
            {
                "subentry_type": "device",
                "title": "Child",
                "unique_id": CHILD_DEVICE_ID,
                "data": data,
            }
        ]
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            return_value=PARENT_MAC,
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == key
    assert entry.error_reason_translation_placeholders == {
        "subentry_id": next(iter(entry.subentries))
    }


async def test_translated_no_platforms(hass: HomeAssistant) -> None:
    """A model without platforms reports a translated setup error."""
    entry = _parent_entry()
    entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            return_value=PARENT_MAC,
        ),
        patch(
            "homeassistant.components.zentraly.get_runtime_platforms", return_value=[]
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.error_reason_translation_key == "no_platforms"


async def test_reconnect_starts_reauth(hass: HomeAssistant) -> None:
    """A loaded entry requests new credentials after a reconnect rejection."""
    entry = _parent_entry()
    entry.add_to_hass(hass)
    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            return_value=PARENT_MAC,
        ),
        patch("homeassistant.components.zentraly.ZentralyApi.async_connect"),
        patch.object(hass.config_entries, "async_forward_entry_setups"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    with patch.object(
        entry.runtime_data.api,
        "_async_connect_once",
        side_effect=ZentralyAuthenticationError,
    ):
        await entry.runtime_data.api._async_connection_loop()
        await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert flows[0]["context"]["entry_id"] == entry.entry_id
    assert flows[0]["step_id"] == "auth"
    assert entry.data[CONF_PASSWORD] == PASSWORD


def _parent_entry(
    *,
    subentries_data: list[dict] | None = None,
) -> MockConfigEntry:
    """Return a mock Zentraly config entry."""

    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=PARENT_DEVICE_ID,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_DEVICE_ID: PARENT_DEVICE_ID,
            CONF_PASSWORD: PASSWORD,
            CONF_MAC: PARENT_MAC,
        },
        subentries_data=subentries_data,
    )


def _zteim_entry() -> MockConfigEntry:
    """Return a mock ZTEIM config entry."""

    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=ZTEIM_DEVICE_ID,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_DEVICE_ID: ZTEIM_DEVICE_ID,
            CONF_PASSWORD: PASSWORD,
            CONF_MAC: ZTEIM_MAC,
        },
    )


async def test_setup_parent_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test setting up a Zentraly parent device."""

    entry = _parent_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            new_callable=AsyncMock,
            return_value=PARENT_MAC,
        ),
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_connect",
            new_callable=AsyncMock,
        ) as mock_connect,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ) as mock_forward,
    ):
        result = await hass.config_entries.async_setup(
            entry.entry_id,
        )

    assert result is True
    assert entry.state is ConfigEntryState.LOADED

    runtime_device = entry.runtime_data.device

    assert entry.runtime_data.api is runtime_device.api

    assert runtime_device.device_id == PARENT_DEVICE_ID
    assert runtime_device.mac == PARENT_MAC
    assert runtime_device.device_model is DeviceModel.ZTTIN

    assert get_device_platforms(PARENT_DEVICE_ID) == frozenset(
        {
            Platform.BUTTON,
            Platform.CLIMATE,
            Platform.SWITCH,
        }
    )

    assert entry.runtime_data.children == {}

    parent_device = device_registry.async_get_device_by_identifier(
        (
            DOMAIN,
            PARENT_DEVICE_ID,
        ),
        entry.entry_id,
    )

    assert parent_device is not None
    assert parent_device.manufacturer == "Zentraly"
    assert parent_device.model == DeviceModel.ZTTIN.value
    assert parent_device.serial_number == PARENT_DEVICE_ID
    assert (
        dr.CONNECTION_NETWORK_MAC,
        dr.format_mac(PARENT_MAC),
    ) in parent_device.connections

    mock_connect.assert_awaited_once()

    mock_forward.assert_awaited_once_with(
        entry,
        [
            Platform.BUTTON,
            Platform.CLIMATE,
            Platform.SWITCH,
        ],
    )


async def test_setup_parent_with_child(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test setting up a Zentraly parent with a child device."""

    entry = _parent_entry(
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_DEVICE,
                "title": CHILD_DEVICE_ID,
                "unique_id": CHILD_DEVICE_ID,
                "data": {
                    CONF_DEVICE_ID: CHILD_DEVICE_ID,
                    CONF_MAC: CHILD_MAC,
                },
            }
        ]
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            new_callable=AsyncMock,
            return_value=PARENT_MAC,
        ),
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_connect",
            new_callable=AsyncMock,
        ) as mock_connect,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ) as mock_forward,
    ):
        result = await hass.config_entries.async_setup(
            entry.entry_id,
        )

    assert result is True
    assert entry.state is ConfigEntryState.LOADED

    runtime_data = entry.runtime_data

    assert len(runtime_data.children) == 1

    child = next(iter(runtime_data.children.values()))

    assert child.device_id == CHILD_DEVICE_ID
    assert child.mac == CHILD_MAC
    assert child.device_model is DeviceModel.ZTBIN

    assert get_device_platforms(CHILD_DEVICE_ID) == frozenset(
        {
            Platform.BINARY_SENSOR,
            Platform.BUTTON,
            Platform.SENSOR,
            Platform.SWITCH,
        }
    )

    # Parent and child must use exactly the same gateway API.
    assert runtime_data.device.api is runtime_data.api
    assert child.api is runtime_data.api

    parent_device = device_registry.async_get_device_by_identifier(
        (
            DOMAIN,
            PARENT_DEVICE_ID,
        ),
        entry.entry_id,
    )

    child_device = device_registry.async_get_device_by_identifier(
        (
            DOMAIN,
            CHILD_DEVICE_ID,
        ),
        entry.entry_id,
    )

    assert parent_device is not None
    assert child_device is not None

    assert parent_device.manufacturer == "Zentraly"
    assert parent_device.model == DeviceModel.ZTTIN.value
    assert parent_device.serial_number == PARENT_DEVICE_ID
    assert (
        dr.CONNECTION_NETWORK_MAC,
        dr.format_mac(PARENT_MAC),
    ) in parent_device.connections

    assert child_device.manufacturer == "Zentraly"
    assert child_device.model == DeviceModel.ZTBIN.value
    assert child_device.serial_number == CHILD_DEVICE_ID
    assert (
        dr.CONNECTION_NETWORK_MAC,
        dr.format_mac(CHILD_MAC),
    ) in child_device.connections

    assert child_device.via_device_id == parent_device.id

    mock_connect.assert_awaited_once()
    mock_forward.assert_awaited_once()

    forward_entry, forward_platforms = mock_forward.await_args.args

    assert forward_entry is entry
    assert set(forward_platforms) == {
        Platform.BUTTON,
        Platform.CLIMATE,
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
        Platform.SWITCH,
    }


async def test_setup_zteim_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test setting up an independent ZTEIM device."""

    entry = _zteim_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            new_callable=AsyncMock,
            return_value=ZTEIM_MAC,
        ),
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_connect",
            new_callable=AsyncMock,
        ) as mock_connect,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ) as mock_forward,
    ):
        result = await hass.config_entries.async_setup(
            entry.entry_id,
        )

    assert result is True
    assert entry.state is ConfigEntryState.LOADED

    runtime_device = entry.runtime_data.device

    assert entry.runtime_data.api is runtime_device.api
    assert runtime_device.device_id == ZTEIM_DEVICE_ID
    assert runtime_device.mac == ZTEIM_MAC
    assert runtime_device.device_model is DeviceModel.ZTEIM
    assert entry.runtime_data.children == {}

    assert get_device_platforms(ZTEIM_DEVICE_ID) == frozenset(
        {
            Platform.BUTTON,
            Platform.NUMBER,
            Platform.SELECT,
            Platform.SENSOR,
            Platform.SWITCH,
        }
    )

    registry_device = device_registry.async_get_device_by_identifier(
        (
            DOMAIN,
            ZTEIM_DEVICE_ID,
        ),
        entry.entry_id,
    )

    assert registry_device is not None
    assert registry_device.manufacturer == "Zentraly"
    assert registry_device.model == DeviceModel.ZTEIM.value
    assert registry_device.serial_number == ZTEIM_DEVICE_ID
    assert (
        dr.CONNECTION_NETWORK_MAC,
        dr.format_mac(ZTEIM_MAC),
    ) in registry_device.connections

    mock_connect.assert_awaited_once()
    mock_forward.assert_awaited_once_with(
        entry,
        [
            Platform.BUTTON,
            Platform.NUMBER,
            Platform.SELECT,
            Platform.SENSOR,
            Platform.SWITCH,
        ],
    )


async def test_setup_unexpected_mac(
    hass: HomeAssistant,
) -> None:
    """Test setup retries when the discovered MAC does not match."""

    entry = _parent_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            new_callable=AsyncMock,
            return_value="001122334455",
        ),
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_connect",
            new_callable=AsyncMock,
        ) as mock_connect,
    ):
        result = await hass.config_entries.async_setup(
            entry.entry_id,
        )

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_RETRY

    mock_connect.assert_not_awaited()


async def test_unload_parent_with_child(
    hass: HomeAssistant,
) -> None:
    """Test unloading a parent also unloads child platforms and connection."""

    entry = _parent_entry(
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_DEVICE,
                "title": CHILD_DEVICE_ID,
                "unique_id": CHILD_DEVICE_ID,
                "data": {
                    CONF_DEVICE_ID: CHILD_DEVICE_ID,
                    CONF_MAC: CHILD_MAC,
                },
            }
        ]
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_validate_password",
            new_callable=AsyncMock,
            return_value=PARENT_MAC,
        ),
        patch(
            "homeassistant.components.zentraly.ZentralyApi.async_connect",
            new_callable=AsyncMock,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new_callable=AsyncMock,
        ),
    ):
        setup_result = await hass.config_entries.async_setup(
            entry.entry_id,
        )

    assert setup_result is True
    assert entry.state is ConfigEntryState.LOADED

    with (
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_unload_platforms,
        patch.object(
            entry.runtime_data.api,
            "async_disconnect",
            new_callable=AsyncMock,
        ) as mock_disconnect,
    ):
        result = await hass.config_entries.async_unload(
            entry.entry_id,
        )

    assert result is True
    assert entry.state is ConfigEntryState.NOT_LOADED

    mock_unload_platforms.assert_awaited_once()

    unload_entry, unload_platforms = mock_unload_platforms.await_args.args

    assert unload_entry is entry
    assert set(unload_platforms) == {
        Platform.BUTTON,
        Platform.CLIMATE,
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
        Platform.SWITCH,
    }

    mock_disconnect.assert_awaited_once()
