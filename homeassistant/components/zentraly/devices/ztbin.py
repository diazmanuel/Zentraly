"""Commands for Zentraly ZTBIN devices."""

from typing import Any, override

from ..commands.base import ZentralyDeviceCommands
from ..commands.common import ZentralyCommonCommands
from ..commands.protocol import DataType
from ..device_classes.binary_sensor.capabilities import BinarySensorCapability
from ..device_classes.sensor.capabilities import SensorCapability
from ..device_classes.sensor.types import SensorOutputType


class ZtbinCommands(ZentralyDeviceCommands):
    """Commands supported by ZTBIN devices."""

    ENDPOINT = 1

    capabilities = frozenset(
        {
            BinarySensorCapability.ON_OFF,
            BinarySensorCapability.FORCED_MODE,
            SensorCapability.ERRORS,
            SensorCapability.OUTPUT_TYPE,
            SensorCapability.RSSI,
        }
    )
    # On/off state
    ON_OFF_CLUSTER = 65006
    ON_OFF_ATTRIBUTE_ID = 0
    ON_OFF_ATTRIBUTE_TYPE = DataType.INT16

    # Forced mode
    FORCED_MODE_CLUSTER = 65006
    FORCED_MODE_ATTRIBUTE_ID = 2
    FORCED_MODE_ATTRIBUTE_TYPE = DataType.INT16

    # Device errors
    ERRORS_CLUSTER = 65535
    ERRORS_ATTRIBUTE_ID = 5
    ERRORS_ATTRIBUTE_TYPE = DataType.INT16

    # Output type
    OUTPUT_TYPE_CLUSTER = 65535
    OUTPUT_TYPE_ATTRIBUTE_ID = 1000
    OUTPUT_TYPE_ATTRIBUTE_TYPE = DataType.INT16

    # RSSI
    RSSI_CLUSTER = 65534
    RSSI_ATTRIBUTE_ID = 200
    RSSI_ATTRIBUTE_TYPE = DataType.INT16

    #
    # Generic ZTBIN helpers
    #

    @classmethod
    def _build_read_attribute(
        cls,
        *,
        rid: int,
        mac: str,
        cluster: int,
        attribute_id: int,
        data_type: int,
    ) -> dict[str, Any]:
        """Build a ZTBIN single-attribute read command."""

        return ZentralyCommonCommands.build_read_attr(
            rid=rid,
            mac=mac,
            cluster=cluster,
            ep=cls.ENDPOINT,
            attrs=[
                {
                    "id": attribute_id,
                    "type": data_type,
                }
            ],
        )

    @staticmethod
    def _parse_attribute_value(
        attrs: list[dict[str, Any]],
        attribute_id: int,
    ) -> Any:
        """Return a requested attribute value."""

        for attr in attrs:
            if not isinstance(attr, dict):
                continue

            if attr.get("id") != attribute_id:
                continue

            if "val" not in attr:
                raise ValueError(f"Missing value for ZTBIN attribute {attribute_id}")

            return attr["val"]

        raise ValueError(f"ZTBIN attribute {attribute_id} not found in response")

    @staticmethod
    def _parse_integer(value: Any) -> int:
        """Validate and return an integer attribute."""

        if not isinstance(value, int):
            raise TypeError("Expected integer ZTBIN attribute value")

        return value

    @staticmethod
    def _parse_binary_value(
        value: Any,
        attribute_name: str,
    ) -> bool:
        """Validate and convert a binary ZTBIN attribute."""

        raw_value = ZtbinCommands._parse_integer(value)

        if raw_value not in (0, 1):
            raise ValueError(f"Invalid ZTBIN {attribute_name} value: {raw_value}")

        return raw_value == 1

    @staticmethod
    def _output_type_from_raw(
        value: int,
    ) -> SensorOutputType:
        """Convert a raw ZTBIN output type."""

        if value == 0:
            return SensorOutputType.ON_OFF

        if value == 1:
            return SensorOutputType.OPENTHERM

        raise ValueError(f"Invalid ZTBIN output type value: {value}")

    #
    # Reports
    #

    def parse_report_entry(
        self,
        entry: dict[str, Any],
    ) -> tuple[BinarySensorCapability | SensorCapability, Any] | None:
        """Parse a supported ZTBIN report entry."""

        if entry.get("mac") not in (None, "") and not isinstance(
            entry.get("mac"),
            str,
        ):
            return None

        if entry.get("ep") != self.ENDPOINT:
            return None

        cluster = entry.get("cluster")
        attribute_id = entry.get("id")

        if not isinstance(cluster, int):
            return None

        if not isinstance(attribute_id, int):
            return None

        if "val" not in entry:
            return None

        value = entry["val"]

        if cluster == self.ON_OFF_CLUSTER and attribute_id == self.ON_OFF_ATTRIBUTE_ID:
            return (
                BinarySensorCapability.ON_OFF,
                self._parse_binary_value(
                    value,
                    "on/off",
                ),
            )

        if (
            cluster == self.FORCED_MODE_CLUSTER
            and attribute_id == self.FORCED_MODE_ATTRIBUTE_ID
        ):
            return (
                BinarySensorCapability.FORCED_MODE,
                self._parse_binary_value(
                    value,
                    "forced mode",
                ),
            )

        if cluster == self.ERRORS_CLUSTER and attribute_id == self.ERRORS_ATTRIBUTE_ID:
            return (
                SensorCapability.ERRORS,
                self._parse_integer(value),
            )

        if (
            cluster == self.OUTPUT_TYPE_CLUSTER
            and attribute_id == self.OUTPUT_TYPE_ATTRIBUTE_ID
        ):
            raw_value = self._parse_integer(value)

            return (
                SensorCapability.OUTPUT_TYPE,
                self._output_type_from_raw(raw_value),
            )

        if cluster == self.RSSI_CLUSTER and attribute_id == self.RSSI_ATTRIBUTE_ID:
            return (
                SensorCapability.RSSI,
                self._parse_integer(value),
            )

        return None

    #
    # MAC address
    #
    @override
    def get_mac_command(
        self,
        rid: int,
    ) -> dict[str, Any]:
        """Return the command to read the device MAC."""

        raise NotImplementedError("ZTBIN devices do not support MAC discovery")

    @override
    def parse_mac_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> str:
        """Parse the MAC address from a ZTBIN response."""

        raise NotImplementedError("ZTBIN devices do not support MAC discovery")

    #
    # Child-device validation
    #
    @override
    def build_validation_command(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the ZTBIN child-device validation command."""

        return self.build_read_on_off(
            rid,
            mac,
        )

    @override
    def parse_validation_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate a ZTBIN child-device response."""

        self.parse_on_off_response(
            response,
            expected_rid,
        )

    #
    # On/off state - R
    #

    def build_read_on_off(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the on/off state read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.ON_OFF_CLUSTER,
            attribute_id=self.ON_OFF_ATTRIBUTE_ID,
            data_type=self.ON_OFF_ATTRIBUTE_TYPE,
        )

    def parse_on_off_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse the ZTBIN on/off state."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        value = self._parse_attribute_value(
            attrs,
            self.ON_OFF_ATTRIBUTE_ID,
        )

        return self._parse_binary_value(
            value,
            "on/off",
        )

    #
    # Forced mode - R
    #

    def build_read_forced_mode(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the forced mode read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.FORCED_MODE_CLUSTER,
            attribute_id=self.FORCED_MODE_ATTRIBUTE_ID,
            data_type=self.FORCED_MODE_ATTRIBUTE_TYPE,
        )

    def parse_forced_mode_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse the ZTBIN forced mode."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        value = self._parse_attribute_value(
            attrs,
            self.FORCED_MODE_ATTRIBUTE_ID,
        )

        return self._parse_binary_value(
            value,
            "forced mode",
        )

    #
    # Device errors - R
    #

    def build_read_errors(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the device errors read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.ERRORS_CLUSTER,
            attribute_id=self.ERRORS_ATTRIBUTE_ID,
            data_type=self.ERRORS_ATTRIBUTE_TYPE,
        )

    def parse_errors_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the ZTBIN error value."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        return self._parse_integer(
            self._parse_attribute_value(
                attrs,
                self.ERRORS_ATTRIBUTE_ID,
            )
        )

    #
    # Output type - R
    #

    def build_read_output_type(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the output type read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OUTPUT_TYPE_CLUSTER,
            attribute_id=self.OUTPUT_TYPE_ATTRIBUTE_ID,
            data_type=self.OUTPUT_TYPE_ATTRIBUTE_TYPE,
        )

    def parse_output_type_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> SensorOutputType:
        """Parse the ZTBIN output type."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        raw_value = self._parse_integer(
            self._parse_attribute_value(
                attrs,
                self.OUTPUT_TYPE_ATTRIBUTE_ID,
            )
        )

        return self._output_type_from_raw(raw_value)

    #
    # RSSI - Report only
    #

    def parse_rssi_report_value(
        self,
        value: Any,
    ) -> int:
        """Parse a ZTBIN RSSI report value in dBm."""

        return self._parse_integer(value)
