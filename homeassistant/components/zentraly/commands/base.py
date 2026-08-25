"""Base commands for Zentraly devices."""

from typing import Any


class ZentralyDeviceCommands:
    """Base commands for Zentraly devices."""

    def get_mac_command(
        self,
        rid: int,
    ) -> dict[str, Any]:
        """Return the command to read the device MAC."""

        raise NotImplementedError("This Zentraly device does not support MAC discovery")

    def parse_mac_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> str:
        """Parse the MAC address from a device response."""

        raise NotImplementedError("This Zentraly device does not support MAC discovery")

    def build_validation_command(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Return a command used to validate a child device."""

        raise NotImplementedError(
            "This Zentraly device does not support child-device validation"
        )

    def parse_validation_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate a child-device validation response."""

        raise NotImplementedError(
            "This Zentraly device does not support child-device validation"
        )
