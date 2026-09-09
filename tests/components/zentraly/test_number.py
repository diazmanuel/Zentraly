"""Tests for Zentraly timer selection races."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from homeassistant.components.zentraly.device_classes.number.api import (
    ZentralyNumberApi,
)
from homeassistant.components.zentraly.device_classes.number.capabilities import (
    NumberCapability,
)
from homeassistant.components.zentraly.exceptions import ZentralyConnectionError
from homeassistant.components.zentraly.models import ZentralyDevice
from homeassistant.components.zentraly.number import ZentralyNumber
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


@pytest.fixture
def number_api() -> MagicMock:
    """Return a timer API with deterministic responses."""
    api = MagicMock(spec=ZentralyNumberApi)
    api.get_range.return_value = (0, 120, 1)
    api.async_set_timer = AsyncMock(return_value=True)
    api.async_get_timer = AsyncMock(return_value=10.0)
    return api


@pytest.fixture
def timer(hass: HomeAssistant, number_api: MagicMock) -> Generator[ZentralyNumber]:
    """Return a timer entity with state publishing isolated from platform setup."""
    device = MagicMock(spec=ZentralyDevice)
    device.device_id = "ZTEIM0100000001"
    device.connected = True
    entity = ZentralyNumber(
        device=device, number_api=number_api, capability=NumberCapability.TIMER
    )
    entity.hass = hass
    entity.entity_id = "number.zentraly_timer"
    with patch.object(entity, "async_write_ha_state"):
        yield entity


@pytest.fixture
def schedule() -> Generator[MagicMock]:
    """Capture debounce callbacks so tests control when each write starts."""
    with patch("homeassistant.components.zentraly.number.async_call_later") as mock:
        yield mock


@pytest.mark.parametrize(
    "success", [pytest.param(True, id="success"), pytest.param(False, id="failure")]
)
async def test_old_write_keeps_new_selection(
    timer: ZentralyNumber,
    number_api: MagicMock,
    schedule: MagicMock,
    success: bool,
) -> None:
    """Finishing the 30-minute write cannot replace a pending 40-minute selection."""
    started = asyncio.Event()
    result = asyncio.get_running_loop().create_future()

    async def write(value: float) -> bool:
        started.set()
        return await result

    number_api.async_set_timer.side_effect = write
    await timer.async_set_native_value(30)
    task = asyncio.create_task(schedule.call_args.args[2](dt_util.utcnow()))
    await started.wait()
    await timer.async_set_native_value(40)
    result.set_result(success)
    await task

    assert timer.native_value == 40
    number_api.async_get_timer.assert_not_awaited()
    number_api.async_set_timer.assert_awaited_once_with(30)

    await schedule.call_args.args[2](dt_util.utcnow())
    assert number_api.async_set_timer.await_args_list == [call(30), call(40)]


async def test_recovery_read_keeps_new_selection(
    timer: ZentralyNumber,
    number_api: MagicMock,
    schedule: MagicMock,
) -> None:
    """A recovery read started before a new selection cannot overwrite it."""
    started = asyncio.Event()
    result = asyncio.get_running_loop().create_future()

    async def read() -> float:
        started.set()
        return await result

    number_api.async_set_timer.return_value = False
    number_api.async_get_timer.side_effect = read
    await timer.async_set_native_value(30)
    task = asyncio.create_task(schedule.call_args.args[2](dt_util.utcnow()))
    await started.wait()
    await timer.async_set_native_value(40)
    result.set_result(10.0)
    await task

    assert timer.native_value == 40
    number_api.async_get_timer.assert_awaited_once()


async def test_timer_debounce(
    hass: HomeAssistant,
    timer: ZentralyNumber,
    number_api: MagicMock,
    schedule: MagicMock,
) -> None:
    """Only the latest selection is scheduled, using the existing three seconds."""
    await timer.async_set_native_value(30)
    cancel = schedule.return_value
    await timer.async_set_native_value(40)

    cancel.assert_called_once_with()
    assert schedule.call_args.args[:2] == (hass, 3.0)
    number_api.async_set_timer.assert_not_awaited()
    await schedule.call_args.args[2](dt_util.utcnow())
    number_api.async_set_timer.assert_awaited_once_with(40)
    assert timer.native_value == 40


async def test_current_write_failure_recovers_device_value(
    timer: ZentralyNumber, number_api: MagicMock, schedule: MagicMock
) -> None:
    """Keep recovery when there is no newer selection."""
    number_api.async_set_timer.return_value = False
    await timer.async_set_native_value(30)
    await schedule.call_args.args[2](dt_util.utcnow())

    number_api.async_get_timer.assert_awaited_once()
    assert timer.native_value == 10.0


async def test_deferred_error_is_logged_and_recovers(
    timer: ZentralyNumber,
    number_api: MagicMock,
    schedule: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Deferred actions report failure in logs and restore the device value."""
    number_api.async_set_timer.side_effect = ZentralyConnectionError("No response")
    await timer.async_set_native_value(30)
    await schedule.call_args.args[2](dt_util.utcnow())
    assert "Timer write failed" in caplog.text
    assert timer.native_value == 10.0
    number_api.async_get_timer.assert_awaited_once()


@pytest.mark.parametrize(
    "success", [pytest.param(True, id="success"), pytest.param(False, id="failure")]
)
async def test_old_write_finishes_after_new_write(
    timer: ZentralyNumber,
    number_api: MagicMock,
    schedule: MagicMock,
    success: bool,
) -> None:
    """Keep the latest value even after its debounce and write have completed."""
    started = asyncio.Event()
    result = asyncio.get_running_loop().create_future()

    async def write(value: float) -> bool:
        started.set()
        return await result

    number_api.async_set_timer.side_effect = write
    await timer.async_set_native_value(30)
    task = asyncio.create_task(schedule.call_args.args[2](dt_util.utcnow()))
    await started.wait()
    await timer.async_set_native_value(40)
    number_api.async_set_timer.side_effect = None
    await schedule.call_args.args[2](dt_util.utcnow())
    result.set_result(success)
    await task

    assert timer.native_value == 40
    assert number_api.async_set_timer.await_args_list == [call(30), call(40)]
    number_api.async_get_timer.assert_not_awaited()
