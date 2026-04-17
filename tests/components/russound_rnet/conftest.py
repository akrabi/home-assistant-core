"""Common fixtures for the Russound RNET tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.russound_rnet.const import (
    CONF_SOURCES,
    CONF_ZONES,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_PORT

from tests.common import MockConfigEntry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="192.168.1.10:9621",
        data={
            CONF_HOST: "192.168.1.10",
            CONF_PORT: 9621,
            CONF_SOURCES: {"1": "TV", "2": "Radio"},
            CONF_ZONES: {"1": "Living Room", "2": "Kitchen"},
        },
        unique_id=None,
    )


@pytest.fixture
def mock_russound_client() -> Generator[AsyncMock]:
    """Return a mocked RussoundRNETClient."""
    with patch(
        "homeassistant.components.russound_rnet.RussoundRNETClient",
        autospec=True,
    ) as mock_cls:
        instance = mock_cls.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()
        instance.is_connected = True
        zone_info = MagicMock()
        zone_info.power = True
        zone_info.source = 1
        zone_info.volume = 25
        instance.get_all_zone_info = AsyncMock(return_value=zone_info)
        instance.set_zone_power = AsyncMock()
        instance.set_volume = AsyncMock()
        instance.select_source = AsyncMock()
        instance.toggle_mute = AsyncMock()
        yield instance
