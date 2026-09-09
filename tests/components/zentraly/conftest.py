"""Fixtures for Zentraly tests."""

import asyncio
from collections.abc import AsyncIterator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from homeassistant.components.zentraly.connection import ZentralyConnection
from homeassistant.components.zentraly.models import ZentralyDevice


@pytest.fixture
async def transport() -> AsyncIterator[tuple[ZentralyConnection, MagicMock]]:
    """Open transport loops with a controlled WebSocket."""
    incoming: asyncio.Queue[aiohttp.WSMessage] = asyncio.Queue()

    async def receive() -> AsyncIterator[aiohttp.WSMessage]:
        while True:
            yield await incoming.get()

    websocket = MagicMock(spec=aiohttp.ClientWebSocketResponse)
    websocket.closed = False
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock()
    websocket.__aiter__.side_effect = receive
    session = MagicMock(spec=aiohttp.ClientSession)
    session.ws_connect = AsyncMock(return_value=websocket)
    session.close = AsyncMock()
    connection = ZentralyConnection("192.168.1.42", 80)
    with patch(
        "homeassistant.components.zentraly.connection.aiohttp.ClientSession",
        return_value=session,
    ):
        await connection.async_connect()
        try:
            yield connection, websocket
        finally:
            await connection.async_disconnect()


@pytest.fixture
def platform_device() -> MagicMock:
    """Return a connected device for isolated platform behavior tests."""
    device = MagicMock(spec=ZentralyDevice)
    device.device_id = "ZTTIN0100000631"
    device.connected = True
    device.opentherm_connected = True
    return device


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock setting up a Zentraly config entry."""

    with patch(
        "homeassistant.components.zentraly.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup
