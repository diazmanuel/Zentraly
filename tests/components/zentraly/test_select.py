"""Tests for Zentraly operating mode selection."""

from contextlib import AbstractContextManager, nullcontext
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.zentraly.device_classes.select.api import (
    ZentralySelectApi,
)
from homeassistant.components.zentraly.device_classes.select.capabilities import (
    SelectCapability,
)
from homeassistant.components.zentraly.device_classes.types import SelectOperationMode
from homeassistant.components.zentraly.select import ZentralySelect
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.parametrize(
    ("success", "expected", "expectation"),
    [
        pytest.param(True, "auto", nullcontext(), id="success"),
        pytest.param(False, "manual", pytest.raises(HomeAssistantError), id="failure"),
    ],
)
async def test_select_mode(
    platform_device: MagicMock,
    success: bool,
    expected: str,
    expectation: AbstractContextManager,
) -> None:
    """Only a successful command changes the displayed option."""
    api = MagicMock(spec=ZentralySelectApi)
    api.get_options.return_value = [
        SelectOperationMode.MANUAL,
        SelectOperationMode.AUTO,
    ]
    api.async_get_operation_mode.return_value = SelectOperationMode.MANUAL
    api.async_set_operation_mode.return_value = success
    entity = ZentralySelect(
        device=platform_device,
        select_api=api,
        capability=SelectCapability.OPERATION_MODE,
    )
    await entity.async_update()
    with patch.object(entity, "async_write_ha_state"), expectation:
        await entity.async_select_option("auto")
    assert entity.current_option == expected
    assert entity.options == ["manual", "auto"]
    api.async_set_operation_mode.assert_awaited_once_with(SelectOperationMode.AUTO)


async def test_disconnected_select(platform_device: MagicMock) -> None:
    """Do not send a mode change through a disconnected gateway."""
    platform_device.connected = False
    api = MagicMock(spec=ZentralySelectApi)
    api.get_options.return_value = [SelectOperationMode.AUTO]
    entity = ZentralySelect(
        device=platform_device,
        select_api=api,
        capability=SelectCapability.OPERATION_MODE,
    )
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("auto")
    api.async_set_operation_mode.assert_not_awaited()
