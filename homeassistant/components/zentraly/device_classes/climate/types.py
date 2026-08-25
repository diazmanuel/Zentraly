"""Generic climate definitions for Zentraly devices."""

from enum import Enum


class ClimateOperationMode(Enum):
    """Generic Zentraly climate operation modes."""

    OFF = "off"
    MANUAL = "manual"
    AUTO = "auto"
    AWAY = "away"
