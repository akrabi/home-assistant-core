"""Tests for the Russound RNET config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant.components.russound_rnet.const import (
    CONF_ENABLED_ZONES,
    CONF_SOURCES,
    CONF_ZONES,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from tests.common import MockConfigEntry

PATCH_RNET_CLIENT = (
    "homeassistant.components.russound_rnet.config_flow.RussoundRNETClient"
)
PATCH_TCP_HANDLER = (
    "homeassistant.components.russound_rnet.config_flow.RussoundTcpConnectionHandler"
)
PATCH_SETUP_ENTRY = "homeassistant.components.russound_rnet.async_setup_entry"


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """Test successful user flow with 3 steps."""
    with (
        patch(PATCH_RNET_CLIENT, autospec=True) as mock_cls,
        patch(PATCH_TCP_HANDLER),
        patch(PATCH_SETUP_ENTRY, return_value=True),
    ):
        instance = mock_cls.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()

        # Step 1: connection and sources
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.10",
                CONF_PORT: 9621,
                "controllers": 1,
                "source_1": "TV",
                "source_2": "Radio",
            },
        )

        # Step 2: select zones
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "zones"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ENABLED_ZONES: ["1", "2", "3"]},
        )

        # Step 3: name zones
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "zone_names"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "zone_1": "Living Room",
                "zone_2": "Kitchen",
                "zone_3": "Bedroom",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.168.1.10:9621"
    assert result["data"] == {
        CONF_HOST: "192.168.1.10",
        CONF_PORT: 9621,
        CONF_SOURCES: {"1": "TV", "2": "Radio"},
        CONF_ZONES: {
            "1": "Living Room",
            "2": "Kitchen",
            "3": "Bedroom",
            "4": "Zone 4",
            "5": "Zone 5",
            "6": "Zone 6",
        },
    }
    assert result["options"] == {CONF_ENABLED_ZONES: ["1", "2", "3"]}


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """Test user flow with connection error."""
    with (
        patch(PATCH_RNET_CLIENT, autospec=True) as mock_cls,
        patch(PATCH_TCP_HANDLER),
    ):
        instance = mock_cls.return_value
        instance.connect = AsyncMock(side_effect=ConnectionRefusedError)
        instance.disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.10",
                CONF_PORT: 9621,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unknown_error(hass: HomeAssistant) -> None:
    """Test user flow with unknown error."""
    with (
        patch(PATCH_RNET_CLIENT, autospec=True) as mock_cls,
        patch(PATCH_TCP_HANDLER),
    ):
        instance = mock_cls.return_value
        instance.connect = AsyncMock(side_effect=RuntimeError("Unexpected"))
        instance.disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.10",
                CONF_PORT: 9621,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured(hass: HomeAssistant) -> None:
    """Test user flow when already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.10",
            CONF_PORT: 9621,
            CONF_SOURCES: {},
            CONF_ZONES: {"1": "Zone 1"},
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(PATCH_RNET_CLIENT, autospec=True) as mock_cls,
        patch(PATCH_TCP_HANDLER),
    ):
        instance = mock_cls.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.10",
                CONF_PORT: 9621,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_import_flow_success(hass: HomeAssistant) -> None:
    """Test successful YAML import flow."""
    with (
        patch(PATCH_RNET_CLIENT, autospec=True) as mock_cls,
        patch(PATCH_TCP_HANDLER),
        patch(PATCH_SETUP_ENTRY, return_value=True),
    ):
        instance = mock_cls.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_HOST: "192.168.1.10",
                CONF_PORT: 9621,
                CONF_SOURCES: {"1": "TV", "2": "Radio"},
                CONF_ZONES: {"1": "Living Room", "2": "Kitchen"},
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "192.168.1.10:9621"
    assert result["data"][CONF_SOURCES] == {"1": "TV", "2": "Radio"}
    assert result["data"][CONF_ZONES] == {"1": "Living Room", "2": "Kitchen"}


async def test_import_flow_cannot_connect(hass: HomeAssistant) -> None:
    """Test YAML import flow with connection error."""
    with (
        patch(PATCH_RNET_CLIENT, autospec=True) as mock_cls,
        patch(PATCH_TCP_HANDLER),
    ):
        instance = mock_cls.return_value
        instance.connect = AsyncMock(side_effect=ConnectionRefusedError)
        instance.disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_HOST: "192.168.1.10",
                CONF_PORT: 9621,
                CONF_SOURCES: {},
                CONF_ZONES: {},
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_import_flow_already_configured(hass: HomeAssistant) -> None:
    """Test YAML import flow when already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.10",
            CONF_PORT: 9621,
            CONF_SOURCES: {},
            CONF_ZONES: {"1": "Zone 1"},
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(PATCH_RNET_CLIENT, autospec=True) as mock_cls,
        patch(PATCH_TCP_HANDLER),
    ):
        instance = mock_cls.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_HOST: "192.168.1.10",
                CONF_PORT: 9621,
                CONF_SOURCES: {},
                CONF_ZONES: {},
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_russound_client: AsyncMock,
) -> None:
    """Test options flow for source name configuration."""
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "source_1": "Spotify",
            "source_3": "Vinyl",
            CONF_ENABLED_ZONES: ["1", "2"],
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SOURCES: {"1": "Spotify", "3": "Vinyl"},
        CONF_ENABLED_ZONES: ["1", "2"],
    }


async def test_options_flow_disable_zone(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_russound_client: AsyncMock,
) -> None:
    """Test options flow to disable a zone."""
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "source_1": "TV",
            CONF_ENABLED_ZONES: ["1"],
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENABLED_ZONES] == ["1"]
