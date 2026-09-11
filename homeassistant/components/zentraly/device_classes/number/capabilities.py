"""Capability definitions for Zentraly number devices."""

from enum import Enum


class NumberCapability(Enum):
    """Supported Zentraly number capabilities."""

    TIMER = "timer"

    HIGH_VOLTAGE_LIMIT = "high_voltage_limit"
    LOW_VOLTAGE_LIMIT = "low_voltage_limit"
    HIGH_POWER_LIMIT = "high_power_limit"
    TIMER_OFF = "timer_off"
