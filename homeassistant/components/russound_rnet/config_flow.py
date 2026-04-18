"""Config flow for Russound RNET integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from aiorussound import RussoundTcpConnectionHandler
from aiorussound.rnet.client import RussoundRNETClient
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.typing import VolDictType

from .const import (
    CONF_ENABLED_ZONES,
    CONF_SOURCE_1,
    CONF_SOURCE_2,
    CONF_SOURCE_3,
    CONF_SOURCE_4,
    CONF_SOURCE_5,
    CONF_SOURCE_6,
    CONF_SOURCES,
    CONF_ZONES,
    DOMAIN,
    MAX_CONTROLLERS,
    RNET_EXCEPTIONS,
    ZONES_PER_CONTROLLER,
)

_LOGGER = logging.getLogger(__name__)

SOURCES = [
    CONF_SOURCE_1,
    CONF_SOURCE_2,
    CONF_SOURCE_3,
    CONF_SOURCE_4,
    CONF_SOURCE_5,
    CONF_SOURCE_6,
]

OPTIONS_FOR_DATA: VolDictType = {vol.Optional(source): str for source in SOURCES}

CONF_CONTROLLERS = "controllers"

CONNECT_RETRIES = 3
CONNECT_RETRY_DELAY = 1.0

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=9621): int,
        vol.Required(CONF_CONTROLLERS, default=1): NumberSelector(
            NumberSelectorConfig(
                min=1, max=MAX_CONTROLLERS, step=1, mode=NumberSelectorMode.BOX
            )
        ),
        **OPTIONS_FOR_DATA,
    }
)


@callback
def _sources_from_config(data: dict[str, Any]) -> dict[str, str]:
    """Build sources dict from config flow input."""
    sources_config = {
        str(idx + 1): data.get(source) for idx, source in enumerate(SOURCES)
    }
    return {
        index: name.strip()
        for index, name in sources_config.items()
        if name is not None and name.strip() != ""
    }


@callback
def _schema_with_defaults(user_input: dict[str, Any] | None) -> vol.Schema:
    """Build the data schema with suggested values from previous input."""
    if user_input is None:
        return DATA_SCHEMA

    schema: VolDictType = {}
    for key in DATA_SCHEMA.schema:
        if isinstance(key, (vol.Optional, vol.Required)) and key.schema in user_input:
            default = key.default() if callable(key.default) else key.default
            description = {"suggested_value": user_input[key.schema]}
            new_key: vol.Optional | vol.Required
            if isinstance(key, vol.Optional):
                new_key = vol.Optional(
                    key.schema, default=default, description=description
                )
            else:
                new_key = vol.Required(
                    key.schema, default=default, description=description
                )
            schema[new_key] = DATA_SCHEMA.schema[key]
        else:
            schema[key] = DATA_SCHEMA.schema[key]
    return vol.Schema(schema)


async def _async_validate_connection(host: str, port: int) -> None:
    """Validate the user input allows us to connect.

    Retries up to CONNECT_RETRIES times with a delay between attempts,
    since the RNET protocol can be flaky on initial connection.
    """
    last_err: Exception | None = None
    for attempt in range(CONNECT_RETRIES):
        client = RussoundRNETClient(RussoundTcpConnectionHandler(host, port))
        try:
            await client.connect()
        except RNET_EXCEPTIONS as err:
            last_err = err
            _LOGGER.debug(
                "Connection attempt %d/%d to %s:%s failed: %s",
                attempt + 1,
                CONNECT_RETRIES,
                host,
                port,
                err,
            )
            if attempt < CONNECT_RETRIES - 1:
                await asyncio.sleep(CONNECT_RETRY_DELAY)
        else:
            return
        finally:
            with contextlib.suppress(*RNET_EXCEPTIONS):
                await client.disconnect()
    if last_err is not None:
        raise last_err


class RussoundRNETConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Russound RNET."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._total_zones: int = 0
        self._selected_zones: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 1: connection and sources."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
            try:
                await _async_validate_connection(host, port)
            except RNET_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                num_controllers = int(user_input.get(CONF_CONTROLLERS, 1))
                self._total_zones = num_controllers * ZONES_PER_CONTROLLER
                self._data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_SOURCES: _sources_from_config(user_input),
                }
                return await self.async_step_zones()

        return self.async_show_form(
            step_id="user",
            data_schema=_schema_with_defaults(user_input),
            errors=errors,
        )

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 2: select which zones to enable."""
        all_zone_ids = [str(i) for i in range(1, self._total_zones + 1)]

        if user_input is not None:
            self._selected_zones = user_input.get(CONF_ENABLED_ZONES, all_zone_ids)
            return await self.async_step_zone_names()

        zone_options = [
            SelectOptionDict(value=str(i), label=f"Zone {i}")
            for i in range(1, self._total_zones + 1)
        ]

        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLED_ZONES, default=all_zone_ids
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=zone_options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_zone_names(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 3: name the selected zones."""
        if user_input is not None:
            # Store ALL zones in data (selected get custom names, others get defaults)
            all_zone_ids = [str(i) for i in range(1, self._total_zones + 1)]
            zones = {}
            for zone_id in all_zone_ids:
                if zone_id in self._selected_zones:
                    zones[zone_id] = user_input.get(
                        f"zone_{zone_id}", f"Zone {zone_id}"
                    )
                else:
                    zones[zone_id] = f"Zone {zone_id}"
            return self.async_create_entry(
                title=f"{self._data[CONF_HOST]}:{self._data[CONF_PORT]}",
                data={
                    **self._data,
                    CONF_ZONES: zones,
                },
                options={CONF_ENABLED_ZONES: self._selected_zones},
            )

        schema: VolDictType = {}
        for zone_id in self._selected_zones:
            schema[vol.Required(f"zone_{zone_id}", default=f"Zone {zone_id}")] = str

        return self.async_show_form(
            step_id="zone_names",
            data_schema=vol.Schema(schema),
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle import from YAML configuration."""
        self._async_abort_entries_match(
            {CONF_HOST: import_data[CONF_HOST], CONF_PORT: import_data[CONF_PORT]}
        )

        try:
            await _async_validate_connection(
                import_data[CONF_HOST], import_data[CONF_PORT]
            )
        except RNET_EXCEPTIONS:
            return self.async_abort(reason="cannot_connect")

        sources = import_data.get(CONF_SOURCES, {})
        zones = import_data.get(CONF_ZONES, {})

        return self.async_create_entry(
            title=f"{import_data[CONF_HOST]}:{import_data[CONF_PORT]}",
            data={
                CONF_HOST: import_data[CONF_HOST],
                CONF_PORT: import_data[CONF_PORT],
                CONF_SOURCES: sources,
                CONF_ZONES: zones,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> RussoundRNETOptionsFlowHandler:
        """Define the config flow to handle options."""
        return RussoundRNETOptionsFlowHandler()


@callback
def _key_for_source(
    index: int, source: str, previous_sources: dict[str, str]
) -> vol.Optional:
    """Build a vol.Optional key with suggested value if source was previously set."""
    if str(index) in previous_sources:
        return vol.Optional(
            source, description={"suggested_value": previous_sources[str(index)]}
        )
    return vol.Optional(source)


class RussoundRNETOptionsFlowHandler(OptionsFlow):
    """Handle Russound RNET options."""

    @callback
    def _previous_sources(self) -> dict[str, str]:
        """Get previous source configuration."""
        if CONF_SOURCES in self.config_entry.options:
            return self.config_entry.options[CONF_SOURCES]
        return self.config_entry.data.get(CONF_SOURCES, {})

    @callback
    def _all_zones(self) -> dict[str, str]:
        """Get all available zones from config data."""
        return self.config_entry.data.get(CONF_ZONES, {})

    @callback
    def _enabled_zones(self) -> list[str]:
        """Get currently enabled zone IDs."""
        if CONF_ENABLED_ZONES in self.config_entry.options:
            return self.config_entry.options[CONF_ENABLED_ZONES]
        # Default: all zones enabled
        return list(self._all_zones().keys())

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_SOURCES: _sources_from_config(user_input),
                    CONF_ENABLED_ZONES: user_input.get(
                        CONF_ENABLED_ZONES, list(self._all_zones().keys())
                    ),
                },
            )

        previous_sources = self._previous_sources()
        all_zones = self._all_zones()
        enabled_zones = self._enabled_zones()

        # Build zone select options
        zone_select_options = [
            SelectOptionDict(value=zone_id, label=zone_name)
            for zone_id, zone_name in all_zones.items()
        ]

        options: VolDictType = {
            _key_for_source(idx + 1, source, previous_sources): str
            for idx, source in enumerate(SOURCES)
        }
        options[vol.Optional(CONF_ENABLED_ZONES, default=enabled_zones)] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=zone_select_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options),
        )
