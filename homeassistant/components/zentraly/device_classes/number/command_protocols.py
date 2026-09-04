"""Command capability protocols for Zentraly number devices."""

from typing import Any, Protocol


class TimerCommands(Protocol):
    """Commands for devices supporting a timer."""

    def build_read_timer(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the timer read command."""

    def parse_timer_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse the timer duration response."""

    def build_write_timer(
        self,
        rid: int,
        mac: str,
        value: float,
        power_on: bool,
    ) -> dict[str, Any]:
        """Build the timer write command."""

    def parse_write_timer_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Parse the timer write response."""


class HighVoltageLimitCommands(Protocol):
    """Commands for devices supporting a high-voltage limit."""

    def build_read_high_voltage_limit(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the high-voltage-limit read command."""

    def parse_high_voltage_limit_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse the high-voltage-limit response."""

    def build_write_high_voltage_limit(
        self,
        rid: int,
        mac: str,
        value: float,
    ) -> dict[str, Any]:
        """Build the high-voltage-limit write command."""

    def parse_write_high_voltage_limit_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Parse the high-voltage-limit write response."""


class LowVoltageLimitCommands(Protocol):
    """Commands for devices supporting a low-voltage limit."""

    def build_read_low_voltage_limit(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the low-voltage-limit read command."""

    def parse_low_voltage_limit_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse the low-voltage-limit response."""

    def build_write_low_voltage_limit(
        self,
        rid: int,
        mac: str,
        value: float,
    ) -> dict[str, Any]:
        """Build the low-voltage-limit write command."""

    def parse_write_low_voltage_limit_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Parse the low-voltage-limit write response."""


class HighPowerLimitCommands(Protocol):
    """Commands for devices supporting a high-power limit."""

    def build_read_high_power_limit(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the high-power-limit read command."""

    def parse_high_power_limit_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse the high-power-limit response."""

    def build_write_high_power_limit(
        self,
        rid: int,
        mac: str,
        value: float,
    ) -> dict[str, Any]:
        """Build the high-power-limit write command."""

    def parse_write_high_power_limit_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Parse the high-power-limit write response."""
