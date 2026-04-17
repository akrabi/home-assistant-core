"""Support for interfacing with Russound via RNET Protocol."""

from __future__ import annotations

import math

from aiorussound.rnet.client import RNETZoneInfo

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RussoundRNETConfigEntry
from .const import CONF_ENABLED_ZONES, CONF_SOURCES, CONF_ZONES, DOMAIN
from .coordinator import RussoundRNETCoordinator


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
    coordinator = config_entry.runtime_data
    sources = _get_sources(config_entry)
    zones = config_entry.data.get(CONF_ZONES, {})

    # Build source maps preserving source IDs (1-based)
    source_id_name = {int(idx): name for idx, name in sources.items()}
    source_name_id = {name: idx for idx, name in source_id_name.items()}
    source_names = [source_id_name[idx] for idx in sorted(source_id_name.keys())]

    # Get enabled zones from options (default: all zones)
    enabled_zones: list[str] | None = config_entry.options.get(CONF_ENABLED_ZONES)

    entities: list[RussoundRNETDevice] = []
    for zone_id_str, zone_name in zones.items():
        if enabled_zones is not None and zone_id_str not in enabled_zones:
            continue
        zone_id = int(zone_id_str)
        entities.append(
            RussoundRNETDevice(
                coordinator,
                source_names,
                source_id_name,
                source_name_id,
                config_entry.entry_id,
                zone_id,
                zone_name,
            )
        )

    async_add_entities(entities)

    # Remove entities and devices for disabled zones
    if enabled_zones is not None:
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        all_zones = config_entry.data.get(CONF_ZONES, {})
        disabled_zone_ids = set(all_zones.keys()) - set(enabled_zones)

        for zone_id_str in disabled_zone_ids:
            zone_id = int(zone_id_str)
            identifier = (DOMAIN, f"{config_entry.entry_id}_{zone_id}")

            entries = er.async_entries_for_config_entry(
                ent_reg, config_entry.entry_id
            )
            for entry in entries:
                if entry.unique_id == f"{config_entry.entry_id}_{zone_id}":
                    ent_reg.async_remove(entry.entity_id)

            device = dev_reg.async_get_device(identifiers={identifier})
            if device is not None:
                dev_reg.async_remove_device(device.id)


class RussoundRNETDevice(
    CoordinatorEntity[RussoundRNETCoordinator], MediaPlayerEntity
):
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
        coordinator: RussoundRNETCoordinator,
        sources: list[str],
        source_id_name: dict[int, str],
        source_name_id: dict[str, int],
        namespace: str,
        zone_id: int,
        zone_name: str,
    ) -> None:
        """Initialize the Russound RNET device."""
        super().__init__(coordinator)
        self._attr_source_list = sources
        self._source_id_name = source_id_name
        self._source_name_id = source_name_id
        self._zone_id = zone_id
        self._controller_id = math.ceil(zone_id / 6)
        self._zone_within = (zone_id - 1) % 6 + 1
        self._attr_unique_id = f"{namespace}_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{namespace}_{zone_id}")},
            manufacturer="Russound",
            model="RNET",
            name=zone_name,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data and self._zone_id in self.coordinator.data:
            info: RNETZoneInfo = self.coordinator.data[self._zone_id]
            self._attr_available = True
            self._attr_state = (
                MediaPlayerState.ON if info.power else MediaPlayerState.OFF
            )
            self._attr_volume_level = info.volume / 50.0
            source_id = info.source
            if source_id in self._source_id_name:
                self._attr_source = self._source_id_name[source_id]
        else:
            self._attr_available = False
        self.async_write_ha_state()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self.coordinator.async_send_command(
            self.coordinator.client.set_volume,
            self._controller_id,
            self._zone_within,
            round(volume * 50),
        )

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self.coordinator.async_send_command(
            self.coordinator.client.set_zone_power,
            self._controller_id,
            self._zone_within,
            True,
        )

    async def async_turn_off(self) -> None:
        """Turn off media player."""
        await self.coordinator.async_send_command(
            self.coordinator.client.set_zone_power,
            self._controller_id,
            self._zone_within,
            False,
        )

    async def async_mute_volume(self, mute: bool) -> None:
        """Send mute command.

        Note: The RNET protocol only supports toggle, not explicit mute state.
        """
        await self.coordinator.async_send_command(
            self.coordinator.client.toggle_mute,
            self._controller_id,
            self._zone_within,
        )

    async def async_select_source(self, source: str) -> None:
        """Set the input source."""
        if source in self._source_name_id:
            source_id = self._source_name_id[source]
            await self.coordinator.async_send_command(
                self.coordinator.client.select_source,
                self._controller_id,
                self._zone_within,
                source_id,
            )
