"""The Russound RNET component."""

from __future__ import annotations

import logging

from aiorussound import RussoundTcpConnectionHandler
from aiorussound.rnet.client import RussoundRNETClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_ENABLED_ZONES, CONF_ZONES, DOMAIN, PLATFORMS, RNET_EXCEPTIONS
from .coordinator import RussoundRNETCoordinator

_LOGGER = logging.getLogger(__name__)

type RussoundRNETConfigEntry = ConfigEntry[RussoundRNETCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: RussoundRNETConfigEntry
) -> bool:
    """Set up Russound RNET from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    client = RussoundRNETClient(RussoundTcpConnectionHandler(host, port))

    try:
        await client.connect()
    except RNET_EXCEPTIONS as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": host, "port": str(port)},
        ) from err

    # Determine enabled zones
    zones = entry.data.get(CONF_ZONES, {})
    enabled_zone_strs: list[str] = entry.options.get(
        CONF_ENABLED_ZONES, list(zones.keys())
    )
    zone_ids = sorted(int(z) for z in enabled_zone_strs)

    coordinator = RussoundRNETCoordinator(hass, client, zone_ids)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: RussoundRNETConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        await entry.runtime_data.client.disconnect()

    return unload_ok


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
