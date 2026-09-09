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
    CommandResponse,
    ZentralyConnection,
    ZentralyMessage,
)
from homeassistant.components.zentraly.exceptions import ZentralyConnectionBusyError
from homeassistant.core import HomeAssistant


async def flush_transport(hass: HomeAssistant) -> None:
    """Run transport tasks and their shielded future callbacks."""
    for _ in range(6):
        await asyncio.sleep(0)
    await hass.async_block_till_done()


def queue_read(
    connection: ZentralyConnection, index: int
) -> asyncio.Task[CommandResponse]:
    """Queue an identifiable request for one of two child MACs."""
    return asyncio.create_task(
        connection.async_send_command(
            lambda rid: {
                "cmd": "readAttr",
                "rid": rid,
                "mac": ("aa", "bb")[index % 2],
                "index": index,
            }
        )
    )


async def test_limit_and_fifo(
    hass: HomeAssistant,
    transport: tuple[ZentralyConnection, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Share twenty slots across MACs and keepalive, preserving FIFO order."""
    connection, websocket = transport
    tasks = [queue_read(connection, index) for index in range(31)]
    keepalive = asyncio.create_task(
        connection.async_send_command(ZentralyCommonCommands.build_keepalive)
    )
    await flush_transport(hass)
    assert websocket.send_json.await_count == 20
    assert connection._waiting == 12
    assert caplog.text.count("connection loaded") == 1
    assert caplog.text.count("queue has reached") == 1
    report_listener = MagicMock()
    connection.add_report_listener(report_listener)
    report = {"cmd": "report", "data": [{"mac": "aa", "val": 1}]}
    connection._handle_text_message(json.dumps(report))
    report_listener.assert_called_once_with(report)
    for index in range(12):
        command = websocket.send_json.await_args_list[index].args[0]
        connection._handle_text_message(json.dumps(command | {"status": 200}))
        await flush_transport(hass)
        assert len(connection._pending_requests) == 20
    assert [
        call.args[0]["index"] for call in websocket.send_json.await_args_list[:31]
    ] == list(range(31))
    assert websocket.send_json.await_args_list[-1].args[0]["cmd"] == "aliveLogin"
    assert connection._waiting == 0
    assert caplog.text.count("connection loaded") == 13
    await connection.async_disconnect()
    await asyncio.gather(*tasks, keepalive)
    assert connection._requests == {}
    assert connection._pending_requests == {}
    assert connection._send_queue.empty()


async def test_waiting_log_rearms(
    hass: HomeAssistant,
    transport: tuple[ZentralyConnection, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only crossing ten waiting requests logs, with no rejection above ten."""
    connection, _ = transport
    active = [queue_read(connection, index) for index in range(20)]
    await flush_transport(hass)
    caplog.clear()
    waiting = [queue_read(connection, index) for index in range(11)]
    await flush_transport(hass)
    assert connection._waiting == 11
    assert caplog.text.count("queue has reached") == 1
    for task in waiting[:3]:
        task.cancel()
    await asyncio.gather(*waiting[:3], return_exceptions=True)
    assert connection._waiting == 8
    extra = [queue_read(connection, index) for index in range(3)]
    await flush_transport(hass)
    assert connection._waiting == 11
    assert caplog.text.count("queue has reached") == 2
    await connection.async_disconnect()
    await asyncio.gather(*active, *waiting, *extra, return_exceptions=True)


async def test_waiting_rid_is_reserved(
    hass: HomeAssistant, transport: tuple[ZentralyConnection, MagicMock]
) -> None:
    """RID wraparound cannot reuse a request identifier that is still queued."""
    connection, websocket = transport
    tasks = [queue_read(connection, index) for index in range(21)]
    await flush_transport(hass)
    connection._rid = 0xFFFF
    extra = queue_read(connection, 22)
    await flush_transport(hass)
    assert len(connection._requests) == 22
    assert 22 in connection._requests
    assert websocket.send_json.await_count == 20
    await connection.async_disconnect()
    assert (await extra)[0] == 22
    await asyncio.gather(*tasks)


async def test_stalled_send_releases_requests(
    hass: HomeAssistant, transport: tuple[ZentralyConnection, MagicMock]
) -> None:
    """A stalled WebSocket write cannot leave its sender or queued work stuck."""
    connection, websocket = transport
    blocked = asyncio.Event()

    async def send(command: ZentralyMessage) -> None:
        await blocked.wait()

    websocket.send_json.side_effect = send
    with patch.object(hass.loop, "time", return_value=hass.loop.time()) as clock:
        tasks = [queue_read(connection, index) for index in range(3)]
        await flush_transport(hass)
        assert websocket.send_json.await_count == 1
        clock.return_value += 31
        await flush_transport(hass)
        assert await asyncio.gather(*tasks) == [(1, None), (2, None), (3, None)]
        assert not connection.connected
        assert connection._requests == {}
        assert connection._waiting == 0
        assert connection._send_queue.empty()


async def test_response_timeout_starts_on_send(
    hass: HomeAssistant, transport: tuple[ZentralyConnection, MagicMock]
) -> None:
    """Time spent waiting does not consume the thirty-second response window."""
    connection, websocket = transport
    with patch.object(hass.loop, "time", return_value=hass.loop.time()) as clock:
        first = [queue_read(connection, index) for index in range(20)]
        await flush_transport(hass)
        clock.return_value += 10
        waiting = queue_read(connection, 20)
        await flush_transport(hass)
        assert websocket.send_json.await_count == 20
        clock.return_value += 21
        await flush_transport(hass)
        assert await asyncio.gather(*first) == [(rid, None) for rid in range(1, 21)]
        assert websocket.send_json.await_count == 21
        clock.return_value += 20
        await flush_transport(hass)
        assert not waiting.done()
        clock.return_value += 11
        await flush_transport(hass)
        assert await waiting == (21, None)


async def test_queue_timeout_never_sends(
    hass: HomeAssistant,
    transport: tuple[ZentralyConnection, MagicMock],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Waiting for sixty seconds fails locally and cannot send later."""
    connection, websocket = transport
    with (
        patch.object(hass.loop, "time", return_value=hass.loop.time()) as clock,
        patch("homeassistant.components.zentraly.connection.COMMAND_TIMEOUT", 120),
    ):
        tasks = [queue_read(connection, index) for index in range(20)]
        await flush_transport(hass)
        waiting = queue_read(connection, 20)
        await flush_transport(hass)
        clock.return_value += 61
        await flush_transport(hass)
        with pytest.raises(ZentralyConnectionBusyError):
            await waiting
        assert connection._waiting == 0
        assert "connection saturated" in caplog.text
        command = websocket.send_json.await_args_list[0].args[0]
        connection._handle_text_message(json.dumps(command | {"status": 200}))
        await flush_transport(hass)
        assert websocket.send_json.await_count == 20
        await connection.async_disconnect()
        await asyncio.gather(*tasks)


@pytest.mark.parametrize(
    "index", [pytest.param(0, id="in-flight"), pytest.param(20, id="waiting")]
)
async def test_cancel_request(
    hass: HomeAssistant, transport: tuple[ZentralyConnection, MagicMock], index: int
) -> None:
    """Cancellation releases the request and skips canceled queue entries."""
    connection, websocket = transport
    tasks = [queue_read(connection, index) for index in range(22)]
    await flush_transport(hass)
    tasks[index].cancel()
    with pytest.raises(asyncio.CancelledError):
        await tasks[index]
    command = websocket.send_json.await_args_list[1].args[0]
    connection._handle_text_message(json.dumps(command | {"status": 200}))
    await flush_transport(hass)
    assert websocket.send_json.await_args_list[-1].args[0]["index"] == 21
    await connection.async_disconnect()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert connection._waiting == 0
    assert connection._requests == {}


@pytest.mark.parametrize(
    "lost",
    [pytest.param(False, id="disconnect"), pytest.param(True, id="transport-loss")],
)
async def test_reconnect_does_not_replay(
    hass: HomeAssistant, transport: tuple[ZentralyConnection, MagicMock], lost: bool
) -> None:
    """Both shutdown paths fail all old requests and start a clean connection."""
    connection, websocket = transport
    tasks = [queue_read(connection, index) for index in range(25)]
    await flush_transport(hass)
    shutdown = {
        False: connection.async_disconnect,
        True: lambda: async_connection_lost(connection),
    }[lost]
    await shutdown()
    await connection.async_connect()
    assert await asyncio.gather(*tasks) == [(rid, None) for rid in range(1, 26)]
    await flush_transport(hass)
    assert websocket.send_json.await_count == 20
    assert connection._waiting == 0
    assert connection._requests == {}
    task = queue_read(connection, 30)
    await flush_transport(hass)
    assert websocket.send_json.await_count == 21
    await connection.async_disconnect()
    assert await task == (26, None)


async def async_connection_lost(connection: ZentralyConnection) -> None:
    """Simulate the receiver detecting an unexpected disconnect."""
    connection._handle_connection_lost("test disconnect")


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"mac": "wrong"}, id="mac"),
        pytest.param({"rid": 99}, id="rid"),
        pytest.param({"cmd": "writeAttr"}, id="command"),
    ],
)
async def test_mismatched_response_keeps_slot(
    hass: HomeAssistant, transport: tuple[ZentralyConnection, MagicMock], change: dict
) -> None:
    """Unrelated responses cannot free another device's request slot."""
    connection, websocket = transport
    tasks = [queue_read(connection, index) for index in range(21)]
    await flush_transport(hass)
    command = websocket.send_json.await_args_list[0].args[0]
    connection._handle_text_message(json.dumps(command | {"status": 200} | change))
    await flush_transport(hass)
    assert websocket.send_json.await_count == 20
    assert not tasks[0].done()
    connection._handle_text_message(json.dumps(command | {"status": 200, "mac": "AA"}))
    await flush_transport(hass)
    assert websocket.send_json.await_count == 21
    await connection.async_disconnect()
    await asyncio.gather(*tasks)


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
