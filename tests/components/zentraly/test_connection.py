"""Tests for Zentraly transport logging."""

import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from homeassistant.components.zentraly.commands.common import ZentralyCommonCommands
from homeassistant.components.zentraly.connection import (
    ZentralyConnection,
    ZentralyMessage,
)


@pytest.mark.parametrize(
    "credentials",
    [
        pytest.param({}, id="login"),
        pytest.param({"password": "top-level-secret"}, id="password"),
        pytest.param(
            {"data": [{"key": "nested-key", "password": "nested-password"}]},
            id="nested-credentials",
        ),
    ],
)
async def test_credentials_redacted_without_changing_messages(
    caplog: pytest.LogCaptureFixture,
    credentials: ZentralyMessage,
) -> None:
    """Redact both directions while preserving wire data and delivered responses."""
    caplog.set_level(
        logging.DEBUG, logger="homeassistant.components.zentraly.connection"
    )
    incoming: asyncio.Queue[aiohttp.WSMessage] = asyncio.Queue()

    async def receive() -> AsyncIterator[aiohttp.WSMessage]:
        while True:
            yield await incoming.get()

    async def send(command: ZentralyMessage) -> None:
        await incoming.put(
            aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, json.dumps(command), "")
        )

    websocket = MagicMock(spec=aiohttp.ClientWebSocketResponse)
    websocket.closed = False
    websocket.send_json = AsyncMock(side_effect=send)
    websocket.__aiter__.side_effect = receive
    websocket.close = AsyncMock()
    session = MagicMock(spec=aiohttp.ClientSession)
    session.ws_connect = AsyncMock(return_value=websocket)
    session.close = AsyncMock()
    connection = ZentralyConnection("192.168.1.42", 12345)
    listener = MagicMock()
    connection.add_message_listener(listener)
    command = ZentralyCommonCommands.build_login(1, "login-secret") | credentials
    original = deepcopy(command)

    with patch(
        "homeassistant.components.zentraly.connection.aiohttp.ClientSession",
        return_value=session,
    ):
        await connection.async_connect()
        try:
            async with asyncio.timeout(5):
                rid, response = await connection.async_send_command(lambda rid: command)
        finally:
            await connection.async_disconnect()

    assert rid == 1
    assert response == original
    assert command == original
    websocket.send_json.assert_awaited_once_with(original)
    listener.assert_called_once_with(original)
    assert "Zentraly WebSocket TX:" in caplog.text
    assert "Zentraly WebSocket RX:" in caplog.text
    assert "'cmd': 'login'" in caplog.text
    assert "'rid': 1" in caplog.text
    assert "**REDACTED**" in caplog.text
    assert "login-secret" not in caplog.text
    assert "top-level-secret" not in caplog.text
    assert "nested-key" not in caplog.text
    assert "nested-password" not in caplog.text


@pytest.mark.parametrize(
    "message",
    [
        pytest.param('{"key": "malformed-secret"', id="invalid-json"),
        pytest.param('[{"password": "malformed-secret"}]', id="json-list"),
        pytest.param('"malformed-secret"', id="json-string"),
    ],
)
def test_invalid_messages_are_not_logged(
    caplog: pytest.LogCaptureFixture, message: str
) -> None:
    """Do not expose raw payloads that cannot be interpreted as protocol messages."""
    caplog.set_level(
        logging.DEBUG, logger="homeassistant.components.zentraly.connection"
    )
    connection = ZentralyConnection("192.168.1.42", 12345)
    listener = MagicMock()
    connection.add_message_listener(listener)

    connection._handle_text_message(message)

    listener.assert_not_called()
    assert "malformed-secret" not in caplog.text
