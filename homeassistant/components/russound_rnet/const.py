"""Constants for the Russound RNET integration."""

import asyncio

from aiorussound import CommandError

from homeassistant.const import Platform

DOMAIN = "russound_rnet"

PLATFORMS = [Platform.MEDIA_PLAYER]

CONF_SOURCES = "sources"
CONF_ZONES = "zones"
CONF_ENABLED_ZONES = "enabled_zones"

CONF_SOURCE_1 = "source_1"
CONF_SOURCE_2 = "source_2"
CONF_SOURCE_3 = "source_3"
CONF_SOURCE_4 = "source_4"
CONF_SOURCE_5 = "source_5"
CONF_SOURCE_6 = "source_6"

MAX_CONTROLLERS = 6
ZONES_PER_CONTROLLER = 6

RNET_EXCEPTIONS = (
    CommandError,
    ConnectionRefusedError,
    TimeoutError,
    asyncio.IncompleteReadError,
    OSError,
)
