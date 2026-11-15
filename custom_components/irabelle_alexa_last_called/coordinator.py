"""Coordinator for the Alexa Last Called sensor.

Uses Amazon's HTTP/2 push channel for near-instant vocal history updates
(the EqualizerStateChange push triggers a vocal history re-fetch inside
aioamazondevices) plus a lightweight periodic sync that refreshes the
session and catches any missed events. The device list is fetched once at
setup (and lazily on demand) - no heavy device/media polling.
"""

from datetime import timedelta
from pathlib import Path
from typing import override

from aioamazondevices.api import AmazonEchoApi
from aioamazondevices.exceptions import (
    CannotAuthenticate,
    CannotConnect,
    CannotRetrieveData,
)
from aioamazondevices.structures import (
    AmazonDevice,
    AmazonSaveDataConfig,
    AmazonVocalRecord,
)
from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_LOGIN_DATA, DOMAIN, LOGGER

SCAN_INTERVAL = 300

type AmazonLastCalledConfigEntry = ConfigEntry[AmazonLastCalledCoordinator]


class AmazonLastCalledCoordinator(DataUpdateCoordinator[dict[str, AmazonVocalRecord]]):
    """Coordinator for the Alexa Last Called sensor."""

    config_entry: AmazonLastCalledConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: AmazonLastCalledConfigEntry,
        session: ClientSession,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=entry.title,
            config_entry=entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = AmazonEchoApi(
            session,
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            save_data=AmazonSaveDataConfig(path=Path(hass.config.path(DOMAIN))),
            login_data=entry.data[CONF_LOGIN_DATA],
        )
        self._devices: dict[str, AmazonDevice] = {}
        self.api.on_history_event.append(self.history_state_event_handler)
        self.api.on_history_event.freeze()

    @override
    async def _async_update_data(self) -> dict[str, AmazonVocalRecord]:
        """Lightweight sync: refresh the session and vocal history."""
        try:
            await self.api.login.login_mode_stored_data()
            fetched = await self.api.sync_history_state()
            return {**(self.data or {}), **fetched}
        except CannotConnect as err:
            raise UpdateFailed(f"Unable to connect to Amazon: {err}") from err
        except CannotRetrieveData as err:
            raise UpdateFailed(f"Unable to retrieve data from Amazon: {err}") from err
        except CannotAuthenticate as err:
            raise ConfigEntryAuthFailed(
                f"Invalid authentication with Amazon: {err}"
            ) from err
        except ValueError as err:
            raise UpdateFailed(f"Unable to retrieve data from Amazon: {err}") from err

    async def async_sync_devices(self) -> None:
        """Fetch the device list (best-effort, once at setup)."""
        try:
            self._devices = await self.api.get_devices_data()
        except Exception as err:  # noqa: BLE001 - never block setup
            LOGGER.warning("Device list fetch failed (names may be missing): %s", err)

    async def history_state_event_handler(
        self, vocal_records: dict[str, AmazonVocalRecord]
    ) -> None:
        """Handle pushed vocal record events (near-instant)."""
        unknown = [s for s in vocal_records if s not in self._devices]
        if unknown:
            # Lazily refresh the device list when a record references an
            # unknown serial (best-effort, non-blocking).
            await self.async_sync_devices()
        self.data = {**(self.data or {}), **vocal_records}
        self.async_update_listeners()

    @property
    def devices(self) -> dict[str, AmazonDevice]:
        """Devices (serial -> device)."""
        return self._devices

    @property
    def latest_vocal_record(self) -> tuple[str, AmazonVocalRecord] | None:
        """Return the (serial, record) pair with the most recent timestamp."""
        best: tuple[str, AmazonVocalRecord] | None = None
        for serial, record in self.data.items():
            if best is None or record.timestamp > best[1].timestamp:
                best = (serial, record)
        return best
