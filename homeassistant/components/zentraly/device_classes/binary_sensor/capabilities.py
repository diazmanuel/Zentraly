"""Capability definitions for Zentraly binary sensor devices."""

from enum import Enum


class BinarySensorCapability(Enum):
    """Supported Zentraly binary sensor capabilities."""

    ON_OFF = "on_off"
    FORCED_MODE = "forced_mode"
