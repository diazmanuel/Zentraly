"""Tests for the Zentraly config flow."""

from ipaddress import ip_address
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.components.zentraly.config_flow import (
    SUBENTRY_TYPE_DEVICE,
    ZentralyConfigFlow,
)
from homeassistant.components.zentraly.const import DOMAIN
from homeassistant.components.zentraly.exceptions import (
    ZentralyAuthenticationError,
    ZentralyConnectionError,
)
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from tests.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("mock_setup_entry")

DEVICE_ID = "ZTTIN0100000631"
CHILD_DEVICE_ID = "ZTBIN0100000021"
ZTEIM_DEVICE_ID = "ZTEIM0100000001"
UNKNOWN_DEVICE_ID = "ZZZZZ0100000001"

HOST = "192.168.1.42"
NEW_HOST = "192.168.1.43"

PORT = 12345
NEW_PORT = 12346

MAC = "dcda0c58c8d8"
CHILD_MAC = "1020ba12316c"
ZTEIM_MAC = "aabbccddeeff"

PASSWORD = "test-password"


def _zeroconf_info(
    host: str = HOST,
    port: int = PORT,
    device_id: str = DEVICE_ID,
) -> ZeroconfServiceInfo:
    """Return mock Zentraly Zeroconf discovery information."""

    address = ip_address(host)

    return ZeroconfServiceInfo(
        ip_address=address,
        ip_addresses=[address],
        hostname=f"{device_id}.local.",
        name=f"{device_id}._zentraly._tcp.local.",
        port=port,
        properties={},
        type="_zentraly._tcp.local.",
    )


def _parent_entry(
    *,
    state: config_entries.ConfigEntryState = config_entries.ConfigEntryState.LOADED,
    subentries_data: list[dict] | None = None,
) -> MockConfigEntry:
    """Return a mock Zentraly parent config entry."""

    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE_ID,
        state=state,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_DEVICE_ID: DEVICE_ID,
            CONF_PASSWORD: PASSWORD,
            CONF_MAC: MAC,
        },
        subentries_data=subentries_data,
    )


@pytest.mark.parametrize(
    ("device_id", "mac"),
    [
        (DEVICE_ID, MAC),
        (ZTEIM_DEVICE_ID, ZTEIM_MAC),
    ],
)
async def test_zeroconf_auth_success(
    hass: HomeAssistant,
    device_id: str,
    mac: str,
) -> None:
    """Test successful Zeroconf discovery and authentication."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(
            device_id=device_id,
        ),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"

    with patch(
        "homeassistant.components.zentraly.config_flow."
        "ZentralyApi.async_validate_password",
        new_callable=AsyncMock,
        return_value=mac,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: PASSWORD},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == device_id

    assert result["data"] == {
        CONF_HOST: HOST,
        CONF_PORT: PORT,
        CONF_DEVICE_ID: device_id,
        CONF_PASSWORD: PASSWORD,
        CONF_MAC: mac,
    }


async def test_zeroconf_unsupported_device(
    hass: HomeAssistant,
) -> None:
    """Test unsupported Zeroconf devices are ignored."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(
            device_id=CHILD_DEVICE_ID,
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unsupported_device"


async def test_invalid_auth_recovery(
    hass: HomeAssistant,
) -> None:
    """Test recovery after invalid authentication."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(),
    )

    with patch(
        "homeassistant.components.zentraly.config_flow."
        "ZentralyApi.async_validate_password",
        new_callable=AsyncMock,
        side_effect=ZentralyAuthenticationError,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: "wrong-password"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(
        "homeassistant.components.zentraly.config_flow."
        "ZentralyApi.async_validate_password",
        new_callable=AsyncMock,
        return_value=MAC,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: PASSWORD},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == MAC
    assert result["data"][CONF_PASSWORD] == PASSWORD


async def test_cannot_connect_recovery(
    hass: HomeAssistant,
) -> None:
    """Test recovery after a connection error."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(),
    )

    with patch(
        "homeassistant.components.zentraly.config_flow."
        "ZentralyApi.async_validate_password",
        new_callable=AsyncMock,
        side_effect=ZentralyConnectionError,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: PASSWORD},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(
        "homeassistant.components.zentraly.config_flow."
        "ZentralyApi.async_validate_password",
        new_callable=AsyncMock,
        return_value=MAC,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_PASSWORD: PASSWORD},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_zeroconf_already_configured_updates_address(
    hass: HomeAssistant,
) -> None:
    """Test rediscovery updates host and port of an existing entry."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE_ID,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_DEVICE_ID: DEVICE_ID,
            CONF_PASSWORD: PASSWORD,
            CONF_MAC: MAC,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(
            host=NEW_HOST,
            port=NEW_PORT,
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    assert entry.data[CONF_HOST] == NEW_HOST
    assert entry.data[CONF_PORT] == NEW_PORT
    assert entry.data[CONF_DEVICE_ID] == DEVICE_ID
    assert entry.data[CONF_MAC] == MAC
    assert entry.data[CONF_PASSWORD] == PASSWORD


async def test_zeroconf_already_configured_same_address(
    hass: HomeAssistant,
) -> None:
    """Test rediscovery keeps an unchanged host and port."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE_ID,
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_DEVICE_ID: DEVICE_ID,
            CONF_PASSWORD: PASSWORD,
            CONF_MAC: MAC,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    assert entry.data[CONF_HOST] == HOST
    assert entry.data[CONF_PORT] == PORT
    assert entry.data[CONF_DEVICE_ID] == DEVICE_ID
    assert entry.data[CONF_MAC] == MAC
    assert entry.data[CONF_PASSWORD] == PASSWORD


async def test_user_setup_aborts(
    hass: HomeAssistant,
) -> None:
    """Test manual setup is not supported."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "zeroconf_only"


async def test_parent_supports_child_subentry(
    hass: HomeAssistant,
) -> None:
    """Test ZTTIN exposes the child-device subentry type."""

    entry = _parent_entry()

    supported_types = ZentralyConfigFlow.async_get_supported_subentry_types(entry)

    assert supported_types.keys() == {SUBENTRY_TYPE_DEVICE}


async def test_parent_at_child_limit_does_not_support_more_subentries(
    hass: HomeAssistant,
) -> None:
    """Test a ZTTIN with one child does not expose another child flow."""

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

    supported_types = ZentralyConfigFlow.async_get_supported_subentry_types(entry)

    assert supported_types == {}


async def test_zteim_does_not_support_child_subentries(
    hass: HomeAssistant,
) -> None:
    """Test ZTEIM does not expose child-device subentries."""

    entry = MockConfigEntry(
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

    supported_types = ZentralyConfigFlow.async_get_supported_subentry_types(entry)

    assert supported_types == {}


async def test_child_device_success(
    hass: HomeAssistant,
) -> None:
    """Test successfully adding a ZTBIN child device."""

    entry = _parent_entry()
    entry.add_to_hass(hass)

    mock_api = SimpleNamespace(async_validate_child_device=AsyncMock())
    entry.runtime_data = SimpleNamespace(api=mock_api)

    result = await hass.config_entries.subentries.async_init(
        (
            entry.entry_id,
            SUBENTRY_TYPE_DEVICE,
        ),
        context={
            "source": config_entries.SOURCE_USER,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_ID: CHILD_DEVICE_ID,
            CONF_MAC: "10:20:BA:12:31:6C",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == CHILD_DEVICE_ID
    assert result["unique_id"] == CHILD_DEVICE_ID
    assert result["data"] == {
        CONF_DEVICE_ID: CHILD_DEVICE_ID,
        CONF_MAC: CHILD_MAC,
    }

    mock_api.async_validate_child_device.assert_awaited_once_with(
        CHILD_DEVICE_ID,
        CHILD_MAC,
    )

    assert len(entry.subentries) == 1

    subentry = next(iter(entry.subentries.values()))

    assert subentry.title == CHILD_DEVICE_ID
    assert subentry.unique_id == CHILD_DEVICE_ID
    assert subentry.subentry_type == SUBENTRY_TYPE_DEVICE
    assert subentry.data == {
        CONF_DEVICE_ID: CHILD_DEVICE_ID,
        CONF_MAC: CHILD_MAC,
    }


@pytest.mark.parametrize(
    "mac",
    [
        pytest.param("invalid-mac", id="length"),
        pytest.param("1020ba12316g", id="non-hex"),
    ],
)
async def test_child_device_invalid_mac(
    hass: HomeAssistant,
    mac: str,
) -> None:
    """Test an invalid child MAC address is rejected."""

    entry = _parent_entry()
    entry.add_to_hass(hass)

    mock_validate = AsyncMock()

    entry.runtime_data = SimpleNamespace(
        api=SimpleNamespace(async_validate_child_device=mock_validate)
    )

    result = await hass.config_entries.subentries.async_init(
        (
            entry.entry_id,
            SUBENTRY_TYPE_DEVICE,
        ),
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_ID: CHILD_DEVICE_ID,
            CONF_MAC: mac,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_mac"}

    mock_validate.assert_not_awaited()

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_DEVICE_ID: CHILD_DEVICE_ID,
        CONF_MAC: CHILD_MAC,
    }


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        pytest.param(ZentralyConnectionError, "cannot_connect", id="connection"),
        pytest.param(ValueError, "invalid_device", id="value"),
        pytest.param(TypeError, "invalid_device", id="type"),
    ],
)
async def test_child_device_validation_error_recovery(
    hass: HomeAssistant,
    exception: type[Exception],
    error: str,
) -> None:
    """Test a child that cannot be reached is rejected."""

    entry = _parent_entry()
    entry.add_to_hass(hass)

    entry.runtime_data = SimpleNamespace(
        api=SimpleNamespace(
            async_validate_child_device=AsyncMock(side_effect=[exception(), None])
        )
    )

    result = await hass.config_entries.subentries.async_init(
        (
            entry.entry_id,
            SUBENTRY_TYPE_DEVICE,
        ),
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_ID: CHILD_DEVICE_ID,
            CONF_MAC: CHILD_MAC,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_DEVICE_ID: CHILD_DEVICE_ID,
        CONF_MAC: CHILD_MAC,
    }


async def test_child_device_unknown_model(
    hass: HomeAssistant,
) -> None:
    """Test an unknown child-device model is rejected."""

    entry = _parent_entry()
    entry.add_to_hass(hass)

    mock_validate = AsyncMock()

    entry.runtime_data = SimpleNamespace(
        api=SimpleNamespace(async_validate_child_device=mock_validate)
    )

    result = await hass.config_entries.subentries.async_init(
        (
            entry.entry_id,
            SUBENTRY_TYPE_DEVICE,
        ),
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_ID: UNKNOWN_DEVICE_ID,
            CONF_MAC: CHILD_MAC,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unsupported_device"}

    mock_validate.assert_not_awaited()

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_DEVICE_ID: CHILD_DEVICE_ID,
        CONF_MAC: CHILD_MAC,
    }


async def test_zteim_cannot_be_added_as_child(
    hass: HomeAssistant,
) -> None:
    """Test ZTEIM cannot be configured as a child of ZTTIN."""

    entry = _parent_entry()
    entry.add_to_hass(hass)

    mock_validate = AsyncMock()

    entry.runtime_data = SimpleNamespace(
        api=SimpleNamespace(async_validate_child_device=mock_validate)
    )

    result = await hass.config_entries.subentries.async_init(
        (
            entry.entry_id,
            SUBENTRY_TYPE_DEVICE,
        ),
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_ID: ZTEIM_DEVICE_ID,
            CONF_MAC: ZTEIM_MAC,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unsupported_child"}

    mock_validate.assert_not_awaited()

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_DEVICE_ID: CHILD_DEVICE_ID,
        CONF_MAC: CHILD_MAC,
    }


@pytest.mark.parametrize(
    "unique_id",
    [
        pytest.param(CHILD_DEVICE_ID, id="unique-id"),
        pytest.param(None, id="stored-data"),
    ],
)
async def test_child_device_already_configured_as_entry(
    hass: HomeAssistant,
    unique_id: str | None,
) -> None:
    """Test a device already configured independently cannot become a child."""

    parent_entry = _parent_entry()
    parent_entry.add_to_hass(hass)

    parent_entry.runtime_data = SimpleNamespace(
        api=SimpleNamespace(async_validate_child_device=AsyncMock())
    )

    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={
            CONF_DEVICE_ID: CHILD_DEVICE_ID,
            CONF_MAC: CHILD_MAC,
        },
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (
            parent_entry.entry_id,
            SUBENTRY_TYPE_DEVICE,
        ),
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_ID: CHILD_DEVICE_ID,
            CONF_MAC: CHILD_MAC,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}


async def test_child_flow_requires_loaded_parent(
    hass: HomeAssistant,
) -> None:
    """Test child setup requires the parent entry to be loaded."""

    entry = _parent_entry(state=config_entries.ConfigEntryState.NOT_LOADED)
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (
            entry.entry_id,
            SUBENTRY_TYPE_DEVICE,
        ),
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"


@pytest.mark.parametrize(
    "unique_id",
    [pytest.param(DEVICE_ID, id="unique-id"), pytest.param(None, id="stored-data")],
)
async def test_zeroconf_device_already_configured_as_subentry(
    hass: HomeAssistant,
    unique_id: str | None,
) -> None:
    """Test Zeroconf ignores a device already represented by a subentry."""

    parent_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="OTHER_PARENT",
        data={
            CONF_DEVICE_ID: "OTHER_PARENT",
        },
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_DEVICE,
                "title": DEVICE_ID,
                "unique_id": unique_id,
                "data": {
                    CONF_DEVICE_ID: DEVICE_ID,
                    CONF_MAC: MAC,
                },
            }
        ],
    )
    parent_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(
            device_id=DEVICE_ID,
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="missing-id"),
        pytest.param({CONF_DEVICE_ID: 123}, id="invalid-id"),
    ],
)
def test_parent_without_device_id_has_no_subentry_flow(data: dict[str, object]) -> None:
    """An incomplete parent entry cannot expose child setup."""
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    assert ZentralyConfigFlow.async_get_supported_subentry_types(entry) == {}


@pytest.mark.parametrize(
    "device_id",
    [
        pytest.param(None, id="missing-id"),
        pytest.param(ZTEIM_DEVICE_ID, id="unsupported-model"),
    ],
)
async def test_child_flow_parent_changes(
    hass: HomeAssistant, device_id: str | None
) -> None:
    """Recheck the parent when submitting an already open form."""
    entry = _parent_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_DEVICE),
        context={"source": config_entries.SOURCE_USER},
    )
    hass.config_entries.async_update_entry(entry, data={CONF_DEVICE_ID: device_id})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unsupported_parent"


async def test_child_limit_reached_with_form_open(hass: HomeAssistant) -> None:
    """A child added elsewhere prevents another submission."""
    entry = _parent_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_DEVICE),
        context={"source": "device"},
    )
    other = _parent_entry(
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_DEVICE,
                "title": CHILD_DEVICE_ID,
                "unique_id": CHILD_DEVICE_ID,
                "data": {CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
            }
        ]
    )
    hass.config_entries.async_add_subentry(entry, next(iter(other.subentries.values())))
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "max_children"


@pytest.mark.parametrize(
    "unique_id",
    [
        pytest.param(CHILD_DEVICE_ID, id="unique-id"),
        pytest.param(None, id="stored-data"),
    ],
)
async def test_child_already_configured_as_subentry(
    hass: HomeAssistant, unique_id: str | None
) -> None:
    """Reject children belonging to another parent, then allow correction."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICE_ID: "ZTTIN0100000999"},
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_DEVICE,
                "title": CHILD_DEVICE_ID,
                "unique_id": unique_id,
                "data": {CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
            }
        ],
    )
    existing.add_to_hass(hass)
    entry = _parent_entry()
    entry.add_to_hass(hass)
    validate = AsyncMock()
    entry.runtime_data = SimpleNamespace(
        api=SimpleNamespace(async_validate_child_device=validate)
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_DEVICE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
    )
    assert result["errors"] == {"base": "already_configured"}
    validate.assert_not_awaited()
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        user_input={CONF_DEVICE_ID: " ztbin0100000022 ", CONF_MAC: "AA-BB-CC-DD-EE-FF"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_DEVICE_ID: "ZTBIN0100000022",
        CONF_MAC: "aabbccddeeff",
    }
    validate.assert_awaited_once_with("ZTBIN0100000022", "aabbccddeeff")


async def test_zeroconf_ignores_unrelated_subentries(hass: HomeAssistant) -> None:
    """An unrelated child must not prevent discovery of a new parent."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICE_ID: "ZTTIN0100000999"},
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_DEVICE,
                "title": CHILD_DEVICE_ID,
                "unique_id": CHILD_DEVICE_ID,
                "data": {CONF_DEVICE_ID: CHILD_DEVICE_ID, CONF_MAC: CHILD_MAC},
            }
        ],
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zeroconf_info(),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"
