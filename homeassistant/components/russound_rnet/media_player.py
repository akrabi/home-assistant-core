"""Support for interfacing with Russound via RNET Protocol."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math

from aiorussound.rnet.client import RussoundRNETClient

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RussoundRNETConfigEntry
from .const import CONF_ENABLED_ZONES, CONF_SOURCES, CONF_ZONES, DOMAIN, RNET_EXCEPTIONS

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Delay between zone polls to avoid overwhelming serial bridges
_INTER_ZONE_DELAY = 0.3


@callback
def _get_sources(config_entry: RussoundRNETConfigEntry) -> dict[str, str]:
    """Get sources from options or data."""
    if CONF_SOURCES in config_entry.options:
        return config_entry.options[CONF_SOURCES]
    return config_entry.data.get(CONF_SOURCES, {})


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RussoundRNETConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Russound RNET media player platform."""
    client = config_entry.runtime_data
    sources = _get_sources(config_entry)
    zones = config_entry.data.get(CONF_ZONES, {})

    # Build source maps preserving source IDs (1-based)
    # source_id_name: {1: "TV", 3: "Vinyl"} - maps source ID to name
    # source_name_id: {"TV": 1, "Vinyl": 3} - maps name to source ID
    source_id_name = {int(idx): name for idx, name in sources.items()}
    source_name_id = {name: idx for idx, name in source_id_name.items()}
    source_names = [source_id_name[idx] for idx in sorted(source_id_name.keys())]

    entities: list[RussoundRNETDevice] = []

    # Get enabled zones from options (default: all zones)
    enabled_zones: list[str] | None = config_entry.options.get(CONF_ENABLED_ZONES)

    for zone_id_str, zone_name in zones.items():
        if enabled_zones is not None and zone_id_str not in enabled_zones:
            continue
        zone_id = int(zone_id_str)
        entities.append(
            RussoundRNETDevice(
                client,
                source_names,
                source_id_name,
                source_name_id,
                config_entry.entry_id,
                zone_id,
                zone_name,
            )
        )

    async_add_entities(entities, True)

    # Remove entities for disabled zones from the entity registry
    if enabled_zones is not None:
        ent_reg = er.async_get(hass)
        entries = er.async_entries_for_config_entry(ent_reg, config_entry.entry_id)
        for entry in entries:
            # unique_id format: "{entry_id}_{zone_id}"
            parts = entry.unique_id.rsplit("_", 1)
            if len(parts) == 2 and parts[1] not in enabled_zones:
                ent_reg.async_remove(entry.entity_id)


class RussoundRNETDevice(MediaPlayerEntity):
    """Representation of a Russound RNET device."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        client: RussoundRNETClient,
        sources: list[str],
        source_id_name: dict[int, str],
        source_name_id: dict[str, int],
        namespace: str,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the Russound RNET device."""
        self._client = client
        self._attr_source_list = sources
        self._source_id_name = source_id_name
        self._source_name_id = source_name_id
        # Each controller has a maximum of 6 zones, every increment of 6 zones
        # maps to an additional controller for easier backward compatibility
        self._controller_id = math.ceil(zone_id / 6)
        # Each zone resets to 1-6 per controller
        self._zone_id = (zone_id - 1) % 6 + 1
        self._attr_unique_id = f"{namespace}_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{namespace}_{zone_id}")},
            manufacturer="Russound",
            model="RNET",
            name=zone_name,
        )

    async def _ensure_connected(self) -> bool:
        """Ensure the client is connected, reconnecting if needed."""
        if self._client.is_connected:
            return True
        _LOGGER.debug("Reconnecting RNET client")
        with contextlib.suppress(*RNET_EXCEPTIONS):
            await self._client.connect()
            # Small delay after reconnect to let serial bridge settle
            await asyncio.sleep(_INTER_ZONE_DELAY)
            return True
        return False

    async def async_update(self) -> None:
        """Retrieve latest state."""
        # Small delay between zone polls to avoid overwhelming serial bridges
        await asyncio.sleep(_INTER_ZONE_DELAY)

        if not await self._ensure_connected():
            self._attr_available = False
            return

        try:
            info = await self._client.get_all_zone_info(
                self._controller_id, self._zone_id
            )
        except RNET_EXCEPTIONS as err:
            _LOGGER.debug(
                "First poll attempt failed for controller %s zone %s: %s",
                self._controller_id,
                self._zone_id,
                err,
            )
            # Connection likely dropped — reconnect and retry once
            with contextlib.suppress(*RNET_EXCEPTIONS):
                await self._client.disconnect()
            if not await self._ensure_connected():
                self._attr_available = False
                return
            try:
                info = await self._client.get_all_zone_info(
                    self._controller_id, self._zone_id
                )
            except RNET_EXCEPTIONS as err2:
                _LOGGER.warning(
                    "Could not update zone info for controller %s zone %s: %s",
                    self._controller_id,
                    self._zone_id,
                    err2,
                )
                self._attr_available = False
                return

        self._attr_available = True

        if info.power:
            self._attr_state = MediaPlayerState.ON
        else:
            self._attr_state = MediaPlayerState.OFF

        self._attr_volume_level = info.volume / 50.0
        # Source is 1-based from the library model; look up by ID
        source_id = info.source
        if source_id in self._source_id_name:
            self._attr_source = self._source_id_name[source_id]

    async def _send_command(self, func, *args) -> None:
        """Send a command with reconnect retry."""
        try:
            await func(*args)
        except RNET_EXCEPTIONS:
            # Reconnect and retry once
            with contextlib.suppress(*RNET_EXCEPTIONS):
                await self._client.disconnect()
            if await self._ensure_connected():
                await func(*args)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self._send_command(
            self._client.set_volume,
            self._controller_id,
            self._zone_id,
            round(volume * 50),
        )

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self._send_command(
            self._client.set_zone_power,
            self._controller_id,
            self._zone_id,
            True,
        )

    async def async_turn_off(self) -> None:
        """Turn off media player."""
        await self._send_command(
            self._client.set_zone_power,
            self._controller_id,
            self._zone_id,
            False,
        )

    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command.

        Note: The RNET protocol only supports toggle, not explicit mute state.
        """
        await self._send_command(
            self._client.toggle_mute,
            self._controller_id,
            self._zone_id,
        )

    async def async_select_source(self, source: str) -> None:
        """Set the input source."""
        if source in self._source_name_id:
            source_id = self._source_name_id[source]
            await self._send_command(
                self._client.select_source,
                self._controller_id,
                self._zone_id,
                source_id,
            )
