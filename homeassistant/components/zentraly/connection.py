"""WebSocket connection management for Zentraly devices."""

import asyncio
from collections.abc import Callable
from contextlib import suppress
import json
import logging
from typing import Any

import aiohttp

from homeassistant.helpers.redact import async_redact_data

_LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT = 30
MAX_RID = 0xFFFF
TO_REDACT = {"key", "password"}

type ZentralyMessage = dict[str, Any]
type CommandBuilder = Callable[[int], ZentralyMessage]
type CommandResponse = tuple[int, ZentralyMessage | None]
type MessageListener = Callable[[ZentralyMessage], None]
type ReportListener = Callable[[ZentralyMessage], None]
type ConnectionLostListener = Callable[[str], None]
type PendingRequest = tuple[
    str,
    str | None,
    asyncio.Future[ZentralyMessage | None],
]


class ZentralyTransportError(Exception):
    """Error raised when the Zentraly WebSocket transport fails."""


class ZentralyConnection:
    """Manage a Zentraly WebSocket connection."""

    def __init__(
        self,
        host: str,
        port: int,
    ) -> None:
        """Initialize the Zentraly connection."""

        self._host = host
        self._port = port

        self._session: aiohttp.ClientSession | None = None
        self._websocket: aiohttp.ClientWebSocketResponse | None = None

        self._send_queue: asyncio.Queue[ZentralyMessage] = asyncio.Queue()

        self._pending_requests: dict[int, PendingRequest] = {}

        self._sender_task: asyncio.Task[None] | None = None
        self._receiver_task: asyncio.Task[None] | None = None

        self._message_listeners: set[MessageListener] = set()
        self._report_listeners: set[ReportListener] = set()
        self._connection_lost_listeners: set[ConnectionLostListener] = set()

        self._connected = False
        self._rid = 0

    @property
    def connected(self) -> bool:
        """Return whether the WebSocket is connected."""

        return self._connected

    def add_message_listener(
        self,
        listener: MessageListener,
    ) -> Callable[[], None]:
        """Register a valid incoming message listener."""

        self._message_listeners.add(listener)

        def remove_listener() -> None:
            """Remove the message listener."""

            self._message_listeners.discard(listener)

        return remove_listener

    def add_report_listener(
        self,
        listener: ReportListener,
    ) -> Callable[[], None]:
        """Register a report listener."""

        self._report_listeners.add(listener)

        def remove_listener() -> None:
            """Remove the report listener."""

            self._report_listeners.discard(listener)

        return remove_listener

    def add_connection_lost_listener(
        self,
        listener: ConnectionLostListener,
    ) -> Callable[[], None]:
        """Register a connection-lost listener."""

        self._connection_lost_listeners.add(listener)

        def remove_listener() -> None:
            """Remove the connection-lost listener."""

            self._connection_lost_listeners.discard(listener)

        return remove_listener

    def _next_rid(self) -> int:
        """Return the next available request ID for this connection."""

        for _ in range(MAX_RID):
            self._rid += 1

            if self._rid > MAX_RID:
                self._rid = 1

            if self._rid not in self._pending_requests:
                return self._rid

        raise ZentralyTransportError("No Zentraly request IDs available")

    @staticmethod
    def _get_expected_mac(
        command: ZentralyMessage,
    ) -> str | None:
        """Return the expected response MAC for a command."""

        mac = command.get("mac")

        if not isinstance(mac, str) or not mac:
            return None

        return mac

    @staticmethod
    def _response_matches_mac(
        response_command: str,
        expected_mac: str | None,
        response: ZentralyMessage,
    ) -> bool:
        """Return whether a response matches the expected device MAC."""

        if expected_mac is None:
            return True

        # According to the Zentraly protocol, readAttr responses include
        # the device MAC. Other currently supported command responses do not.
        if response_command != "readAttr":
            return True

        response_mac = response.get("mac")

        if not isinstance(response_mac, str) or not response_mac:
            return False

        return response_mac.lower() == expected_mac.lower()

    async def async_connect(self) -> None:
        """Open the WebSocket and start sender and receiver tasks."""

        if self._connected:
            return

        await self.async_disconnect()

        url = f"ws://{self._host}:{self._port}/ws"

        try:
            self._session = aiohttp.ClientSession()
            self._websocket = await self._session.ws_connect(url)

        except (TimeoutError, aiohttp.ClientError, OSError) as err:
            await self._async_close_transport()

            raise ZentralyTransportError(
                f"Unable to open Zentraly WebSocket transport: {err}"
            ) from err

        self._connected = True

        self._sender_task = asyncio.create_task(self._async_sender_loop())
        self._receiver_task = asyncio.create_task(self._async_receiver_loop())

    async def async_disconnect(self) -> None:
        """Close the WebSocket connection."""

        self._connected = False

        sender_task = self._sender_task
        receiver_task = self._receiver_task

        self._sender_task = None
        self._receiver_task = None

        current_task = asyncio.current_task()

        for task in (sender_task, receiver_task):
            if task is None or task is current_task:
                continue

            task.cancel()

            with suppress(asyncio.CancelledError):
                await task

        self._resolve_pending_requests()
        self._clear_send_queue()

        await self._async_close_transport()

    async def async_send_command(
        self,
        command_builder: CommandBuilder,
    ) -> CommandResponse:
        """Build, queue, and wait for a matching command response."""

        rid = self._next_rid()

        if not self._connected or self._websocket is None:
            return rid, None

        command = command_builder(rid)

        command_rid = command.get("rid")
        command_name = command.get("cmd")

        if command_rid != rid:
            raise ValueError("Zentraly command builder returned an unexpected RID")

        if not isinstance(command_name, str) or not command_name:
            raise TypeError("Zentraly command must contain a command name")

        expected_mac = self._get_expected_mac(command)

        future: asyncio.Future[ZentralyMessage | None] = (
            asyncio.get_running_loop().create_future()
        )

        self._pending_requests[rid] = (
            command_name,
            expected_mac,
            future,
        )

        await self._send_queue.put(command)

        try:
            async with asyncio.timeout(COMMAND_TIMEOUT):
                response = await future

        except TimeoutError:
            return rid, None

        else:
            return rid, response

        finally:
            self._pending_requests.pop(rid, None)

    async def _async_sender_loop(self) -> None:
        """Send queued commands over the WebSocket."""

        while self._connected:
            command = await self._send_queue.get()

            try:
                websocket = self._websocket

                if websocket is None or websocket.closed:
                    self._handle_connection_lost(
                        "WebSocket unavailable while sending command"
                    )
                    return

                _LOGGER.debug(
                    "Zentraly WebSocket TX: %s",
                    async_redact_data(command, TO_REDACT),
                )

                await websocket.send_json(command)

            except (aiohttp.ClientError, OSError) as err:
                self._handle_connection_lost(f"Error sending WebSocket message: {err}")
                return

            finally:
                self._send_queue.task_done()

    async def _async_receiver_loop(self) -> None:
        """Receive and dispatch all WebSocket messages."""

        websocket = self._websocket

        if websocket is None:
            return

        try:
            async for message in websocket:
                if message.type == aiohttp.WSMsgType.TEXT:
                    self._handle_text_message(message.data)
                    continue

                if message.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    self._handle_connection_lost(
                        f"WebSocket closed with message type {message.type}"
                    )
                    return

                if message.type == aiohttp.WSMsgType.ERROR:
                    self._handle_connection_lost("WebSocket reported an error")
                    return

        except (aiohttp.ClientError, OSError) as err:
            self._handle_connection_lost(f"Error receiving WebSocket message: {err}")

        else:
            if self._connected:
                self._handle_connection_lost("WebSocket receiver stopped")

    def _handle_text_message(
        self,
        message_data: str,
    ) -> None:
        """Handle a received text WebSocket message."""

        try:
            response = json.loads(message_data)

        except json.JSONDecodeError:
            return

        if not isinstance(response, dict):
            return

        _LOGGER.debug(
            "Zentraly WebSocket RX: %s",
            async_redact_data(response, TO_REDACT),
        )

        response_command = response.get("cmd")

        if not isinstance(response_command, str) or not response_command:
            return

        if response_command == "report":
            self._dispatch_message(response)
            self._dispatch_report(response)
            return

        rid = response.get("rid")

        if not isinstance(rid, int):
            return

        pending_request = self._pending_requests.get(rid)

        if pending_request is None:
            return

        expected_command, expected_mac, future = pending_request

        if response_command != expected_command:
            return

        if not self._response_matches_mac(
            response_command,
            expected_mac,
            response,
        ):
            return

        self._dispatch_message(response)

        if not future.done():
            future.set_result(response)

    def _dispatch_message(
        self,
        message: ZentralyMessage,
    ) -> None:
        """Dispatch a valid incoming Zentraly message."""

        for listener in tuple(self._message_listeners):
            listener(message)

    def _dispatch_report(
        self,
        report: ZentralyMessage,
    ) -> None:
        """Dispatch an unsolicited device report."""

        for listener in tuple(self._report_listeners):
            listener(report)

    def _handle_connection_lost(
        self,
        reason: str,
    ) -> None:
        """Handle an unexpected WebSocket disconnection."""

        if not self._connected:
            return

        self._connected = False

        self._resolve_pending_requests()
        self._clear_send_queue()

        for listener in tuple(self._connection_lost_listeners):
            listener(reason)

    def _resolve_pending_requests(self) -> None:
        """Resolve all pending requests without a response."""

        for _, _, future in self._pending_requests.values():
            if not future.done():
                future.set_result(None)

        self._pending_requests.clear()

    def _clear_send_queue(self) -> None:
        """Remove commands waiting to be sent."""

        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()

            except asyncio.QueueEmpty:
                break

            self._send_queue.task_done()

    async def _async_close_transport(self) -> None:
        """Close WebSocket and HTTP session resources."""

        if self._websocket is not None:
            await self._websocket.close()
            self._websocket = None

        if self._session is not None:
            await self._session.close()
            self._session = None
