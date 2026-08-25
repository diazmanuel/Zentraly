"""Capability definitions for Zentraly sensor devices."""

from enum import Enum


class SensorCapability(Enum):
    """Supported Zentraly sensor capabilities."""

    ERRORS = "errors"
    OUTPUT_TYPE = "output_type"
    RSSI = "rssi"
