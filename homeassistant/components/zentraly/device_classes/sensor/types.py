"""Generic sensor definitions for Zentraly devices."""

from enum import Enum


class SensorOutputType(Enum):
    """Supported Zentraly output types."""

    ON_OFF = "on_off"
    OPENTHERM = "opentherm"
