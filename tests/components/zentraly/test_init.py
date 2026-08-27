"""Tests for the Zentraly integration setup."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.zentraly.const import DOMAIN
from homeassistant.components.zentraly.devices.device import (
    DeviceModel,
    get_device_platforms,
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

from tests.common import MockConfigEntry

PARENT_DEVICE_ID = "ZTTIN0100000631"
CHILD_DEVICE_ID = "ZTBIN0100000021"

HOST = "192.168.1.42"
PORT = 80

PARENT_MAC = "dcda0c58c8d8"
CHILD_MAC = "1020ba12316c"

PASSWORD = "test-password"

SUBENTRY_TYPE_DEVICE = "device"


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


async def test_setup_parent_device(
    hass: HomeAssistant,
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

    assert entry.runtime_data.api is entry.runtime_data.device.api

    assert entry.runtime_data.device.device_id == PARENT_DEVICE_ID
    assert entry.runtime_data.device.mac == PARENT_MAC
    assert entry.runtime_data.device.device_model is DeviceModel.ZTTIN
    assert get_device_platforms(PARENT_DEVICE_ID) == frozenset(
        {
            Platform.CLIMATE,
        }
    )

    assert entry.runtime_data.children == {}

    mock_connect.assert_awaited_once()

    mock_forward.assert_awaited_once_with(
        entry,
        [Platform.CLIMATE],
    )


async def test_setup_parent_with_child(
    hass: HomeAssistant,
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
            Platform.SENSOR,
        }
    )

    # Parent and child must use exactly the same gateway API.
    assert runtime_data.device.api is runtime_data.api
    assert child.api is runtime_data.api

    mock_connect.assert_awaited_once()
    mock_forward.assert_awaited_once()

    forward_entry, forward_platforms = mock_forward.await_args.args

    assert forward_entry is entry
    assert set(forward_platforms) == {
        Platform.CLIMATE,
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
    }


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
        Platform.CLIMATE,
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
    }

    mock_disconnect.assert_awaited_once()
