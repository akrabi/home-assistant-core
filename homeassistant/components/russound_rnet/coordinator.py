"""DataUpdateCoordinator for Russound RNET."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
import contextlib
from datetime import timedelta
import logging
import math
from typing import Any

from aiorussound.rnet.client import RNETZoneInfo, RussoundRNETClient

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import RNET_EXCEPTIONS

_LOGGER = logging.getLogger(__name__)

# Delay between zone polls to be gentle on serial bridges
_INTER_ZONE_DELAY = 0.1


class RussoundRNETCoordinator(DataUpdateCoordinator[dict[int, RNETZoneInfo]]):
    """Coordinator to poll all Russound RNET zones."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: RussoundRNETClient,
        zone_ids: list[int],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Russound RNET",
            update_interval=timedelta(seconds=30),
        )
        self.client = client
        self._zone_ids = zone_ids

    async def _ensure_connected(self) -> None:
        """Ensure the client is connected, reconnecting if needed."""
        if self.client.is_connected:
            return
        _LOGGER.debug("Reconnecting RNET client")
        await self.client.connect()
        # Small delay after reconnect to let serial bridge settle
        await asyncio.sleep(_INTER_ZONE_DELAY)

    async def _async_update_data(self) -> dict[int, RNETZoneInfo]:
        """Fetch zone info for all enabled zones."""
        try:
            await self._ensure_connected()
        except RNET_EXCEPTIONS as err:
            raise UpdateFailed(f"Could not connect to RNET device: {err}") from err

        data: dict[int, RNETZoneInfo] = {}
        for zone_id in self._zone_ids:
            controller_id = math.ceil(zone_id / 6)
            zone_within = (zone_id - 1) % 6 + 1
            try:
                info = await self.client.get_all_zone_info(
                    controller_id, zone_within
                )
            except RNET_EXCEPTIONS as err:
                # Reconnect once and retry this zone
                _LOGGER.debug(
                    "Poll failed for zone %s, reconnecting: %s", zone_id, err
                )
                with contextlib.suppress(*RNET_EXCEPTIONS):
                    await self.client.disconnect()
                try:
                    await self._ensure_connected()
                    info = await self.client.get_all_zone_info(
                        controller_id, zone_within
                    )
                except RNET_EXCEPTIONS as err2:
                    raise UpdateFailed(
                        f"Could not update zone {zone_id}: {err2}"
                    ) from err2

            data[zone_id] = info
            # Small delay between zones to avoid overwhelming serial bridges
            if zone_id != self._zone_ids[-1]:
                await asyncio.sleep(_INTER_ZONE_DELAY)

        return data

    async def async_send_command(
        self, func: Callable[..., Coroutine[Any, Any, Any]], *args: Any,
    ) -> None:
        """Send a command with reconnect retry."""
        try:
            await func(*args)
        except RNET_EXCEPTIONS:
            with contextlib.suppress(*RNET_EXCEPTIONS):
                await self.client.disconnect()
            await self._ensure_connected()
            await func(*args)
