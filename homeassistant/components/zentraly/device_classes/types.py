"""Generic definitions for Zentraly device classes."""

from enum import Enum


class ZentralyOutputType(Enum):
    """Supported Zentraly output types."""

    ON_OFF = "on_off"
    OPENTHERM = "opentherm"


class ClimateOperationMode(Enum):
    """Generic Zentraly climate operation modes."""

    OFF = "off"
    MANUAL = "manual"
    AUTO = "auto"
    AWAY = "away"


class SelectOperationMode(Enum):
    """Generic Zentraly selectable operation modes."""

    OFF = "off"
    MANUAL = "manual"
    AUTO = "auto"
    TIMER = "timer"
