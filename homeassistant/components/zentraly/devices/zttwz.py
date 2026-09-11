"""Commands for Zentraly ZTTWZ devices."""

from enum import IntEnum
from typing import Any, override

from ..commands.base import ZentralyDeviceCommands
from ..commands.common import ZentralyCommonCommands
from ..commands.protocol import DataType
from ..device_classes.binary_sensor.capabilities import BinarySensorCapability
from ..device_classes.button.capabilities import ButtonCapability
from ..device_classes.climate.capabilities import ClimateCapability
from ..device_classes.climate.configuration import ClimateConfiguration
from ..device_classes.sensor.capabilities import SensorCapability
from ..device_classes.switch.capabilities import SwitchCapability
from ..device_classes.types import ClimateOperationMode, ZentralyOutputType


class ZttwzOperationMode(IntEnum):
    """ZTTWZ operating modes."""

    OFF = 0
    USER = 1
    CRONO = 2
    AWAY = 3


ZTTWZ_TO_CLIMATE_OPERATION_MODE = {
    ZttwzOperationMode.OFF: ClimateOperationMode.OFF,
    ZttwzOperationMode.USER: ClimateOperationMode.MANUAL,
    ZttwzOperationMode.CRONO: ClimateOperationMode.AUTO,
    ZttwzOperationMode.AWAY: ClimateOperationMode.AWAY,
}

CLIMATE_TO_ZTTWZ_OPERATION_MODE = {
    climate_mode: zttwz_mode
    for zttwz_mode, climate_mode in ZTTWZ_TO_CLIMATE_OPERATION_MODE.items()
}


class ZttwzCommands(ZentralyDeviceCommands):
    """Commands supported by ZTTWZ devices."""

    climate_configuration = ClimateConfiguration(
        minimum_temperature=5,
        maximum_temperature=30,
        temperature_step=0.5,
        operation_modes=tuple(CLIMATE_TO_ZTTWZ_OPERATION_MODE),
        mode_after_setpoint=ClimateOperationMode.MANUAL,
    )

    ENDPOINT = 1

    capabilities = frozenset(
        {
            ClimateCapability.LOCAL_TEMPERATURE,
            ClimateCapability.TARGET_TEMPERATURE,
            ClimateCapability.OPERATION_MODE,
            ClimateCapability.AWAY_TEMPERATURE,
            ClimateCapability.HEAT_DEMAND,
            ClimateCapability.HUMIDITY,
            SensorCapability.ERROR_ID,
            SensorCapability.OUTPUT_TYPE,
            SensorCapability.WIFI_SIGNAL_POWER,
            SensorCapability.CH_SETPOINT,
            SensorCapability.MODULATION_LEVEL,
            SensorCapability.CH_WATER_PRESSURE,
            SensorCapability.DHW_FLOW_RATE,
            SensorCapability.FEED_TEMPERATURE,
            SensorCapability.DHW_TEMPERATURE,
            SensorCapability.DHW_SETPOINT,
            BinarySensorCapability.OT_HEATING_WATER_ACTIVE,
            BinarySensorCapability.OT_DHW_ENABLED,
            BinarySensorCapability.OT_WINTER_MODE,
            SwitchCapability.CHILD_LOCK,
            SwitchCapability.ALWAYS_ON_DISPLAY,
            SwitchCapability.COMFORT_MODE,
            ButtonCapability.RESET_DEVICE,
            ButtonCapability.RESET_BOILER,
        }
    )

    BASIC_CLUSTER = 65000

    FIRMWARE_VERSION_ATTRIBUTE_ID = 2
    FIRMWARE_VERSION_ATTRIBUTE_TYPE = DataType.CHAR_STRING

    HARDWARE_VERSION_ATTRIBUTE_ID = 3
    HARDWARE_VERSION_ATTRIBUTE_TYPE = DataType.CHAR_STRING

    RESET_DEVICE_ATTRIBUTE_ID = 12
    RESET_DEVICE_ATTRIBUTE_TYPE = DataType.INT16

    WIFI_SIGNAL_POWER_ATTRIBUTE_ID = 14
    WIFI_SIGNAL_POWER_ATTRIBUTE_TYPE = DataType.INT16

    MAC_ATTRIBUTE_ID = 20
    MAC_ATTRIBUTE_TYPE = DataType.CHAR_STRING

    BOILER_STATE_CLUSTER = 65006

    BOILER_ON_ATTRIBUTE_ID = 0
    BOILER_ON_ATTRIBUTE_TYPE = DataType.INT16

    THERMOSTAT_CLUSTER = 65513

    LOCAL_TEMPERATURE_ATTRIBUTE_ID = 0
    LOCAL_TEMPERATURE_ATTRIBUTE_TYPE = DataType.INT16

    HUMIDITY_ATTRIBUTE_ID = 1
    HUMIDITY_ATTRIBUTE_TYPE = DataType.INT16

    HEAT_DEMAND_ATTRIBUTE_ID = 6
    HEAT_DEMAND_ATTRIBUTE_TYPE = DataType.INT16

    AWAY_TEMPERATURE_ATTRIBUTE_ID = 17
    AWAY_TEMPERATURE_ATTRIBUTE_TYPE = DataType.INT16

    TARGET_TEMPERATURE_ATTRIBUTE_ID = 18
    TARGET_TEMPERATURE_ATTRIBUTE_TYPE = DataType.INT16

    OPERATION_MODE_ATTRIBUTE_ID = 28
    OPERATION_MODE_ATTRIBUTE_TYPE = DataType.INT16

    CHILD_LOCK_ATTRIBUTE_ID = 90
    CHILD_LOCK_ATTRIBUTE_TYPE = DataType.INT16

    ALWAYS_ON_DISPLAY_ATTRIBUTE_ID = 101
    ALWAYS_ON_DISPLAY_ATTRIBUTE_TYPE = DataType.INT16

    OPENTHERM_CLUSTER = 65535

    OT_STATUS_ATTRIBUTE_ID = 0
    OT_STATUS_ATTRIBUTE_TYPE = DataType.INT16

    CH_SETPOINT_ATTRIBUTE_ID = 1
    CH_SETPOINT_ATTRIBUTE_TYPE = DataType.INT16

    RESET_BOILER_ATTRIBUTE_ID = 4
    RESET_BOILER_ATTRIBUTE_TYPE = DataType.INT16

    ERROR_ID_ATTRIBUTE_ID = 5
    ERROR_ID_ATTRIBUTE_TYPE = DataType.INT16

    MODULATION_LEVEL_ATTRIBUTE_ID = 17
    MODULATION_LEVEL_ATTRIBUTE_TYPE = DataType.INT16

    CH_WATER_PRESSURE_ATTRIBUTE_ID = 18
    CH_WATER_PRESSURE_ATTRIBUTE_TYPE = DataType.INT16

    DHW_FLOW_RATE_ATTRIBUTE_ID = 19
    DHW_FLOW_RATE_ATTRIBUTE_TYPE = DataType.INT16

    FEED_TEMPERATURE_ATTRIBUTE_ID = 25
    FEED_TEMPERATURE_ATTRIBUTE_TYPE = DataType.INT16

    DHW_TEMPERATURE_ATTRIBUTE_ID = 26
    DHW_TEMPERATURE_ATTRIBUTE_TYPE = DataType.INT16

    DHW_SETPOINT_ATTRIBUTE_ID = 56
    DHW_SETPOINT_ATTRIBUTE_TYPE = DataType.INT16

    OUTPUT_TYPE_ATTRIBUTE_ID = 1000
    OUTPUT_TYPE_ATTRIBUTE_TYPE = DataType.INT16

    COMFORT_MODE_ATTRIBUTE_ID = 10001
    COMFORT_MODE_ATTRIBUTE_TYPE = DataType.INT16

    OT_HEATING_WATER_ACTIVE_BIT = 0
    OT_DHW_ENABLED_BIT = 1
    OT_WINTER_MODE_BIT = 5

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
        """Build a ZTTWZ single-attribute read command."""

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

    @classmethod
    def _build_write_attribute(
        cls,
        *,
        rid: int,
        mac: str,
        cluster: int,
        attribute_id: int,
        data_type: int,
        value: str | int,
    ) -> dict[str, Any]:
        """Build a ZTTWZ single-attribute write command."""

        return ZentralyCommonCommands.build_write_attr(
            rid=rid,
            mac=mac,
            cluster=cluster,
            ep=cls.ENDPOINT,
            attrs=[
                {
                    "id": attribute_id,
                    "type": data_type,
                    "val": value,
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
                raise ValueError(f"Missing value for ZTTWZ attribute {attribute_id}")

            return attr["val"]

        raise ValueError(f"ZTTWZ attribute {attribute_id} not found in response")

    @staticmethod
    def _parse_integer(
        value: Any,
    ) -> int:
        """Validate and return an integer attribute."""

        if not isinstance(value, int):
            raise TypeError("Expected integer ZTTWZ attribute value")

        return value

    @classmethod
    def _parse_binary_value(
        cls,
        value: Any,
        attribute_name: str,
    ) -> bool:
        """Validate and convert a binary ZTTWZ attribute."""

        raw_value = cls._parse_integer(value)

        if raw_value not in (0, 1):
            raise ValueError(f"Invalid ZTTWZ {attribute_name} value: {raw_value}")

        return raw_value == 1

    @staticmethod
    def _temperature_from_raw(
        value: int,
    ) -> float:
        """Convert an x100 temperature value to Celsius."""

        return value / 100

    @staticmethod
    def _temperature_to_raw(
        value: float,
    ) -> int:
        """Convert Celsius to the ZTTWZ x100 representation."""

        return round(value * 100)

    @staticmethod
    def _humidity_from_raw(
        value: int,
    ) -> float:
        """Validate and convert humidity to percentage."""

        if not 0 <= value <= 100:
            raise ValueError(f"Invalid ZTTWZ humidity value: {value}")

        return float(value)

    @staticmethod
    def _operation_mode_from_raw(
        value: int,
    ) -> ClimateOperationMode:
        """Convert a raw ZTTWZ operation mode."""

        try:
            zttwz_mode = ZttwzOperationMode(value)

        except ValueError as err:
            raise ValueError(f"Unsupported ZTTWZ operation mode: {value}") from err

        return ZTTWZ_TO_CLIMATE_OPERATION_MODE[zttwz_mode]

    @staticmethod
    def _output_type_from_raw(
        value: int,
    ) -> ZentralyOutputType:
        """Convert a raw ZTTWZ output type."""

        if value == 0:
            return ZentralyOutputType.ON_OFF

        if value == 1:
            return ZentralyOutputType.OPENTHERM

        raise ValueError(f"Invalid ZTTWZ output type value: {value}")

    @classmethod
    def _parse_read_integer_response(
        cls,
        response: dict[str, Any],
        expected_rid: int,
        attribute_id: int,
    ) -> int:
        """Parse an integer attribute response."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        return cls._parse_integer(
            cls._parse_attribute_value(
                attrs,
                attribute_id,
            )
        )

    @classmethod
    def _parse_read_binary_response(
        cls,
        response: dict[str, Any],
        expected_rid: int,
        attribute_id: int,
        attribute_name: str,
    ) -> bool:
        """Parse a binary attribute response."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        return cls._parse_binary_value(
            cls._parse_attribute_value(
                attrs,
                attribute_id,
            ),
            attribute_name,
        )

    @staticmethod
    def _parse_write_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate a ZTTWZ write response."""

        ZentralyCommonCommands.parse_write_attr_response(
            response,
            expected_rid,
        )

    def parse_report_entry(
        self,
        entry: dict[str, Any],
    ) -> (
        tuple[
            ClimateCapability
            | BinarySensorCapability
            | SensorCapability
            | SwitchCapability,
            Any,
        ]
        | None
    ):
        """Parse a supported ZTTWZ report entry."""

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

        if cluster == self.BOILER_STATE_CLUSTER:
            if attribute_id == self.BOILER_ON_ATTRIBUTE_ID:
                return (
                    BinarySensorCapability.BOILER_ON,
                    ZentralyCommonCommands.parse_on_off_level(value),
                )

        if cluster == self.THERMOSTAT_CLUSTER:
            if attribute_id == self.LOCAL_TEMPERATURE_ATTRIBUTE_ID:
                return (
                    ClimateCapability.LOCAL_TEMPERATURE,
                    self._temperature_from_raw(self._parse_integer(value)),
                )

            if attribute_id == self.HUMIDITY_ATTRIBUTE_ID:
                return (
                    ClimateCapability.HUMIDITY,
                    self._humidity_from_raw(self._parse_integer(value)),
                )

            if attribute_id == self.HEAT_DEMAND_ATTRIBUTE_ID:
                return (
                    ClimateCapability.HEAT_DEMAND,
                    self._parse_binary_value(
                        value,
                        "heat demand",
                    ),
                )

            if attribute_id == self.TARGET_TEMPERATURE_ATTRIBUTE_ID:
                return (
                    ClimateCapability.TARGET_TEMPERATURE,
                    self._temperature_from_raw(self._parse_integer(value)),
                )

            if attribute_id == self.OPERATION_MODE_ATTRIBUTE_ID:
                return (
                    ClimateCapability.OPERATION_MODE,
                    self._operation_mode_from_raw(self._parse_integer(value)),
                )

            if attribute_id == self.CHILD_LOCK_ATTRIBUTE_ID:
                return (
                    SwitchCapability.CHILD_LOCK,
                    self._parse_binary_value(
                        value,
                        "child lock",
                    ),
                )

        if cluster == self.OPENTHERM_CLUSTER:
            if attribute_id == self.ERROR_ID_ATTRIBUTE_ID:
                return (
                    SensorCapability.ERROR_ID,
                    self._parse_integer(value),
                )

            if attribute_id == self.OUTPUT_TYPE_ATTRIBUTE_ID:
                return (
                    SensorCapability.OUTPUT_TYPE,
                    self._output_type_from_raw(self._parse_integer(value)),
                )

        return None

    @override
    def get_mac_command(
        self,
        rid: int,
    ) -> dict[str, Any]:
        """Return the command to read the ZTTWZ MAC address."""

        return self._build_read_attribute(
            rid=rid,
            mac="",
            cluster=self.BASIC_CLUSTER,
            attribute_id=self.MAC_ATTRIBUTE_ID,
            data_type=self.MAC_ATTRIBUTE_TYPE,
        )

    @override
    def parse_mac_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> str:
        """Parse the MAC address from a ZTTWZ response."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        mac = self._parse_attribute_value(
            attrs,
            self.MAC_ATTRIBUTE_ID,
        )

        if not isinstance(mac, str) or not mac:
            raise ValueError("Invalid ZTTWZ MAC address")

        return mac

    @override
    def build_validation_command(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the ZTTWZ child-device validation command."""

        return self.build_read_boiler_on(
            rid,
            mac,
        )

    @override
    def parse_validation_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate a ZTTWZ child-device response."""

        self.parse_boiler_on_response(
            response,
            expected_rid,
        )

    def build_read_firmware_version(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the firmware-version read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.BASIC_CLUSTER,
            attribute_id=self.FIRMWARE_VERSION_ATTRIBUTE_ID,
            data_type=self.FIRMWARE_VERSION_ATTRIBUTE_TYPE,
        )

    def parse_firmware_version_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> str:
        """Parse the firmware version."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        value = self._parse_attribute_value(
            attrs,
            self.FIRMWARE_VERSION_ATTRIBUTE_ID,
        )

        if not isinstance(value, str) or not value:
            raise ValueError("Invalid ZTTWZ firmware version")

        return value

    def build_read_hardware_version(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the hardware-version read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.BASIC_CLUSTER,
            attribute_id=self.HARDWARE_VERSION_ATTRIBUTE_ID,
            data_type=self.HARDWARE_VERSION_ATTRIBUTE_TYPE,
        )

    def parse_hardware_version_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> str:
        """Parse the hardware version."""

        attrs = ZentralyCommonCommands.parse_read_attr_response(
            response,
            expected_rid,
        )

        value = self._parse_attribute_value(
            attrs,
            self.HARDWARE_VERSION_ATTRIBUTE_ID,
        )

        if not isinstance(value, str) or not value:
            raise ValueError("Invalid ZTTWZ hardware version")

        return value

    def build_reset_device(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the device-reset command."""

        return self._build_write_attribute(
            rid=rid,
            mac=mac,
            cluster=self.BASIC_CLUSTER,
            attribute_id=self.RESET_DEVICE_ATTRIBUTE_ID,
            data_type=self.RESET_DEVICE_ATTRIBUTE_TYPE,
            value=1,
        )

    @staticmethod
    def parse_reset_device_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate the device-reset response."""

        ZttwzCommands._parse_write_response(
            response,
            expected_rid,
        )

    def build_read_wifi_signal_power(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the Wi-Fi signal-power read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.BASIC_CLUSTER,
            attribute_id=self.WIFI_SIGNAL_POWER_ATTRIBUTE_ID,
            data_type=self.WIFI_SIGNAL_POWER_ATTRIBUTE_TYPE,
        )

    def parse_wifi_signal_power_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse Wi-Fi signal power in dBm."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.WIFI_SIGNAL_POWER_ATTRIBUTE_ID,
        )

    def build_read_boiler_on(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the boiler-state read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.BOILER_STATE_CLUSTER,
            attribute_id=self.BOILER_ON_ATTRIBUTE_ID,
            data_type=self.BOILER_ON_ATTRIBUTE_TYPE,
        )

    def parse_boiler_on_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse whether the boiler is on."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.BOILER_ON_ATTRIBUTE_ID,
        )

        return ZentralyCommonCommands.parse_on_off_level(raw_value)

    def build_read_local_temperature(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the local-temperature read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.LOCAL_TEMPERATURE_ATTRIBUTE_ID,
            data_type=self.LOCAL_TEMPERATURE_ATTRIBUTE_TYPE,
        )

    def parse_local_temperature_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse local temperature in Celsius."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.LOCAL_TEMPERATURE_ATTRIBUTE_ID,
        )

        return self._temperature_from_raw(raw_value)

    def build_read_humidity(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the humidity read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.HUMIDITY_ATTRIBUTE_ID,
            data_type=self.HUMIDITY_ATTRIBUTE_TYPE,
        )

    def parse_humidity_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse relative humidity percentage."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.HUMIDITY_ATTRIBUTE_ID,
        )

        return self._humidity_from_raw(raw_value)

    def build_read_heat_demand(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the heat-demand read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.HEAT_DEMAND_ATTRIBUTE_ID,
            data_type=self.HEAT_DEMAND_ATTRIBUTE_TYPE,
        )

    def parse_heat_demand_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse whether the thermostat is heating."""

        return self._parse_read_binary_response(
            response,
            expected_rid,
            self.HEAT_DEMAND_ATTRIBUTE_ID,
            "heat demand",
        )

    def build_read_away_temperature(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the away-temperature read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.AWAY_TEMPERATURE_ATTRIBUTE_ID,
            data_type=self.AWAY_TEMPERATURE_ATTRIBUTE_TYPE,
        )

    def parse_away_temperature_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse away temperature in Celsius."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.AWAY_TEMPERATURE_ATTRIBUTE_ID,
        )

        return self._temperature_from_raw(raw_value)

    def build_read_target_temperature(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the target-temperature read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.TARGET_TEMPERATURE_ATTRIBUTE_ID,
            data_type=self.TARGET_TEMPERATURE_ATTRIBUTE_TYPE,
        )

    def parse_target_temperature_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse target temperature in Celsius."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.TARGET_TEMPERATURE_ATTRIBUTE_ID,
        )

        return self._temperature_from_raw(raw_value)

    def build_write_target_temperature(
        self,
        rid: int,
        mac: str,
        temperature: float,
    ) -> dict[str, Any]:
        """Build the target-temperature write command."""

        raw_temperature = self._temperature_to_raw(temperature)

        self.climate_configuration.validate_temperature(
            self._temperature_from_raw(raw_temperature)
        )

        return self._build_write_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.TARGET_TEMPERATURE_ATTRIBUTE_ID,
            data_type=self.TARGET_TEMPERATURE_ATTRIBUTE_TYPE,
            value=raw_temperature,
        )

    @staticmethod
    def parse_write_target_temperature_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate target-temperature write response."""

        ZttwzCommands._parse_write_response(
            response,
            expected_rid,
        )

    def build_read_operation_mode(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the operation-mode read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.OPERATION_MODE_ATTRIBUTE_ID,
            data_type=self.OPERATION_MODE_ATTRIBUTE_TYPE,
        )

    def parse_operation_mode_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> ClimateOperationMode:
        """Parse the ZTTWZ operation mode."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.OPERATION_MODE_ATTRIBUTE_ID,
        )

        return self._operation_mode_from_raw(raw_value)

    def build_write_operation_mode(
        self,
        rid: int,
        mac: str,
        mode: ClimateOperationMode,
    ) -> dict[str, Any]:
        """Build the operation-mode write command."""

        self.climate_configuration.validate_operation_mode(mode)

        try:
            zttwz_mode = CLIMATE_TO_ZTTWZ_OPERATION_MODE[mode]

        except KeyError as err:
            raise ValueError(
                f"Unsupported climate operation mode for ZTTWZ: {mode}"
            ) from err

        return self._build_write_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.OPERATION_MODE_ATTRIBUTE_ID,
            data_type=self.OPERATION_MODE_ATTRIBUTE_TYPE,
            value=int(zttwz_mode),
        )

    @staticmethod
    def parse_write_operation_mode_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate operation-mode write response."""

        ZttwzCommands._parse_write_response(
            response,
            expected_rid,
        )

    def build_read_child_lock(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the child-lock read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.CHILD_LOCK_ATTRIBUTE_ID,
            data_type=self.CHILD_LOCK_ATTRIBUTE_TYPE,
        )

    def parse_child_lock_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse the child-lock state."""

        return self._parse_read_binary_response(
            response,
            expected_rid,
            self.CHILD_LOCK_ATTRIBUTE_ID,
            "child lock",
        )

    def build_write_child_lock(
        self,
        rid: int,
        mac: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Build the child-lock write command."""

        return self._build_write_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.CHILD_LOCK_ATTRIBUTE_ID,
            data_type=self.CHILD_LOCK_ATTRIBUTE_TYPE,
            value=int(enabled),
        )

    @staticmethod
    def parse_write_child_lock_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate child-lock write response."""

        ZttwzCommands._parse_write_response(
            response,
            expected_rid,
        )

    def build_read_always_on_display(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the always-on-display read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.ALWAYS_ON_DISPLAY_ATTRIBUTE_ID,
            data_type=self.ALWAYS_ON_DISPLAY_ATTRIBUTE_TYPE,
        )

    def parse_always_on_display_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse the always-on-display state."""

        return self._parse_read_binary_response(
            response,
            expected_rid,
            self.ALWAYS_ON_DISPLAY_ATTRIBUTE_ID,
            "always-on display",
        )

    def build_write_always_on_display(
        self,
        rid: int,
        mac: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Build the always-on-display write command."""

        return self._build_write_attribute(
            rid=rid,
            mac=mac,
            cluster=self.THERMOSTAT_CLUSTER,
            attribute_id=self.ALWAYS_ON_DISPLAY_ATTRIBUTE_ID,
            data_type=self.ALWAYS_ON_DISPLAY_ATTRIBUTE_TYPE,
            value=int(enabled),
        )

    @staticmethod
    def parse_write_always_on_display_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate always-on-display write response."""

        ZttwzCommands._parse_write_response(
            response,
            expected_rid,
        )

    def _build_read_ot_status(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the OpenTherm-status read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.OT_STATUS_ATTRIBUTE_ID,
            data_type=self.OT_STATUS_ATTRIBUTE_TYPE,
        )

    def _parse_ot_status_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the raw OpenTherm status."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.OT_STATUS_ATTRIBUTE_ID,
        )

    def build_read_ot_heating_water_active(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the heating-water-status read command."""

        return self._build_read_ot_status(
            rid,
            mac,
        )

    def parse_ot_heating_water_active_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse whether heating water is active."""

        status = self._parse_ot_status_response(
            response,
            expected_rid,
        )

        return bool(status & (1 << self.OT_HEATING_WATER_ACTIVE_BIT))

    def build_read_ot_dhw_enabled(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the DHW-enabled-status read command."""

        return self._build_read_ot_status(
            rid,
            mac,
        )

    def parse_ot_dhw_enabled_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse whether domestic hot water is enabled."""

        status = self._parse_ot_status_response(
            response,
            expected_rid,
        )

        return bool(status & (1 << self.OT_DHW_ENABLED_BIT))

    def build_read_ot_winter_mode(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the winter-mode-status read command."""

        return self._build_read_ot_status(
            rid,
            mac,
        )

    def parse_ot_winter_mode_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse whether winter mode is active."""

        status = self._parse_ot_status_response(
            response,
            expected_rid,
        )

        return not bool(status & (1 << self.OT_WINTER_MODE_BIT))

    def build_read_ch_setpoint(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the CH-setpoint read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.CH_SETPOINT_ATTRIBUTE_ID,
            data_type=self.CH_SETPOINT_ATTRIBUTE_TYPE,
        )

    def parse_ch_setpoint_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse the OpenTherm CH setpoint."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.CH_SETPOINT_ATTRIBUTE_ID,
        )

        return raw_value / 100

    def build_reset_boiler(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the OpenTherm boiler-reset command."""

        return self._build_write_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.RESET_BOILER_ATTRIBUTE_ID,
            data_type=self.RESET_BOILER_ATTRIBUTE_TYPE,
            value=1,
        )

    @staticmethod
    def parse_reset_boiler_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate the OpenTherm boiler-reset response."""

        ZttwzCommands._parse_write_response(
            response,
            expected_rid,
        )

    def build_read_error_id(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the OpenTherm error-ID read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.ERROR_ID_ATTRIBUTE_ID,
            data_type=self.ERROR_ID_ATTRIBUTE_TYPE,
        )

    def parse_error_id_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the OpenTherm error ID."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.ERROR_ID_ATTRIBUTE_ID,
        )

    def build_read_modulation_level(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the modulation-level read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.MODULATION_LEVEL_ATTRIBUTE_ID,
            data_type=self.MODULATION_LEVEL_ATTRIBUTE_TYPE,
        )

    def parse_modulation_level_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the OpenTherm modulation level."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.MODULATION_LEVEL_ATTRIBUTE_ID,
        )

    def build_read_ch_water_pressure(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the CH-water-pressure read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.CH_WATER_PRESSURE_ATTRIBUTE_ID,
            data_type=self.CH_WATER_PRESSURE_ATTRIBUTE_TYPE,
        )

    def parse_ch_water_pressure_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the OpenTherm CH water pressure."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.CH_WATER_PRESSURE_ATTRIBUTE_ID,
        )

    def build_read_dhw_flow_rate(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the DHW-flow-rate read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.DHW_FLOW_RATE_ATTRIBUTE_ID,
            data_type=self.DHW_FLOW_RATE_ATTRIBUTE_TYPE,
        )

    def parse_dhw_flow_rate_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the OpenTherm DHW flow rate."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.DHW_FLOW_RATE_ATTRIBUTE_ID,
        )

    def build_read_feed_temperature(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the feed-temperature read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.FEED_TEMPERATURE_ATTRIBUTE_ID,
            data_type=self.FEED_TEMPERATURE_ATTRIBUTE_TYPE,
        )

    def parse_feed_temperature_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the OpenTherm feed temperature."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.FEED_TEMPERATURE_ATTRIBUTE_ID,
        )

    def build_read_dhw_temperature(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the DHW-temperature read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.DHW_TEMPERATURE_ATTRIBUTE_ID,
            data_type=self.DHW_TEMPERATURE_ATTRIBUTE_TYPE,
        )

    def parse_dhw_temperature_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> int:
        """Parse the OpenTherm DHW temperature."""

        return self._parse_read_integer_response(
            response,
            expected_rid,
            self.DHW_TEMPERATURE_ATTRIBUTE_ID,
        )

    def build_read_dhw_setpoint(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the DHW-setpoint read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.DHW_SETPOINT_ATTRIBUTE_ID,
            data_type=self.DHW_SETPOINT_ATTRIBUTE_TYPE,
        )

    def parse_dhw_setpoint_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> float:
        """Parse the OpenTherm DHW setpoint."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.DHW_SETPOINT_ATTRIBUTE_ID,
        )

        return raw_value / 100

    def build_read_output_type(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the output-type read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.OUTPUT_TYPE_ATTRIBUTE_ID,
            data_type=self.OUTPUT_TYPE_ATTRIBUTE_TYPE,
        )

    def parse_output_type_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> ZentralyOutputType:
        """Parse the ZTTWZ output type."""

        raw_value = self._parse_read_integer_response(
            response,
            expected_rid,
            self.OUTPUT_TYPE_ATTRIBUTE_ID,
        )

        return self._output_type_from_raw(raw_value)

    def build_read_comfort_mode(
        self,
        rid: int,
        mac: str,
    ) -> dict[str, Any]:
        """Build the comfort-mode read command."""

        return self._build_read_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.COMFORT_MODE_ATTRIBUTE_ID,
            data_type=self.COMFORT_MODE_ATTRIBUTE_TYPE,
        )

    def parse_comfort_mode_response(
        self,
        response: dict[str, Any],
        expected_rid: int,
    ) -> bool:
        """Parse the OpenTherm comfort-mode state."""

        return self._parse_read_binary_response(
            response,
            expected_rid,
            self.COMFORT_MODE_ATTRIBUTE_ID,
            "comfort mode",
        )

    def build_write_comfort_mode(
        self,
        rid: int,
        mac: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Build the OpenTherm comfort-mode write command."""

        return self._build_write_attribute(
            rid=rid,
            mac=mac,
            cluster=self.OPENTHERM_CLUSTER,
            attribute_id=self.COMFORT_MODE_ATTRIBUTE_ID,
            data_type=self.COMFORT_MODE_ATTRIBUTE_TYPE,
            value=int(enabled),
        )

    @staticmethod
    def parse_write_comfort_mode_response(
        response: dict[str, Any],
        expected_rid: int,
    ) -> None:
        """Validate OpenTherm comfort-mode write response."""

        ZttwzCommands._parse_write_response(
            response,
            expected_rid,
        )
