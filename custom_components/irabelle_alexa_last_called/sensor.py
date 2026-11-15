"""Sensor platform for Alexa Last Called."""

from typing import override

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from .const import LOGGER
from .coordinator import AmazonLastCalledCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[AmazonLastCalledCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Alexa Last Called sensor."""
    coordinator = entry.runtime_data
    async_add_entities([AlexaLastCalledSensor(coordinator)])


class AlexaLastCalledSensor(
    CoordinatorEntity[AmazonLastCalledCoordinator], SensorEntity
):
    """Sensor reporting which Alexa device was last called."""

    _attr_name = "Alexa Last Called"
    _attr_icon = "mdi:amazon-alexa"

    def __init__(self, coordinator: AmazonLastCalledCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{slugify(coordinator.config_entry.unique_id)}-last_called"
        )

    @property
    def native_value(self) -> str | None:
        """Return the name of the device that was last called."""
        latest = self.coordinator.latest_vocal_record
        if latest is None:
            return None
        serial, _record = latest
        device = self.coordinator.devices.get(serial)
        if device is None:
            # Fall back to the serial so the state is never "unknown"
            # when the device list is missing a name.
            return serial
        return device.account_name or serial

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return the details of the last called interaction."""
        latest = self.coordinator.latest_vocal_record
        if latest is None:
            return {}
        serial, record = latest
        return {
            "serial_number": serial,
            "last_called_at": dt_util.utc_from_timestamp(
                record.timestamp / 1000
            ).isoformat(),
            "voice_command": record.title,
            "voice_reply": record.sub_title,
            "intent": record.intent,
        }

    @override
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available
