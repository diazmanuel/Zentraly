"""Tests for Zentraly API diagnostics."""

from unittest.mock import patch

import pytest

from homeassistant.components.zentraly.api import ZentralyApi
from homeassistant.components.zentraly.commands.common import ZentralyCommonCommands
from homeassistant.components.zentraly.connection import CommandBuilder, CommandResponse


async def test_unanswered_command_redacts_password(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Retain command diagnostics without disclosing credentials on timeout."""
    api = ZentralyApi("192.168.1.42", 12345, "login-secret", "ZTTIN0100000631")
    api._connected = True
    command = ZentralyCommonCommands.build_login(1, "login-secret")

    async def no_response(builder: CommandBuilder) -> CommandResponse:
        assert builder(1) == command
        return 1, None

    with patch.object(api._connection, "async_send_command", side_effect=no_response):
        result = await api.async_execute_command(lambda rid: command)

    assert result is None
    assert command["key"] == "login-secret"
    assert "No response received" in caplog.text
    assert "'cmd': 'login'" in caplog.text
    assert "rid=1" in caplog.text
    assert "**REDACTED**" in caplog.text
    assert "login-secret" not in caplog.text
