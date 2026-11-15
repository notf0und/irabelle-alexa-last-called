"""Irabelle Alexa Last Called integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import aiohttp_client, httpx_client
from homeassistant.util.ssl import SSL_ALPN_HTTP11_HTTP2

from .const import DOMAIN
from .coordinator import AmazonLastCalledConfigEntry, AmazonLastCalledCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: AmazonLastCalledConfigEntry
) -> bool:
    """Set up Irabelle Alexa Last Called from a config entry."""
    session = aiohttp_client.async_create_clientsession(hass)
    coordinator = AmazonLastCalledCoordinator(hass, entry, session)

    await coordinator.async_config_entry_first_refresh()

    # Fetch the device list once at setup (names for the sensor state).
    await coordinator.async_sync_devices()

    async def _on_http2_reauth_required() -> None:
        entry.async_start_reauth(hass)

    alexa_httpx_client = httpx_client.get_async_client(
        hass,
        alpn_protocols=SSL_ALPN_HTTP11_HTTP2,
    )

    await coordinator.api.start_http2_processing(
        alexa_httpx_client,
        on_reauth_required=_on_http2_reauth_required,
    )

    async def _async_stop_http2(_event: Event | None = None) -> None:
        """Stop HTTP/2 processing on entry unload or HA shutdown."""
        await coordinator.api.stop_http2_processing()

    entry.async_on_unload(_async_stop_http2)
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_http2)
    )

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
