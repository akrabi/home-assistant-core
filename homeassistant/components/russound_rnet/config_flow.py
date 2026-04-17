"""Config flow for Russound RNET integration."""

from __future__ import annotations

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
from homeassistant.helpers.typing import VolDictType

from .const import (
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

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=9621): int,
        vol.Required(CONF_CONTROLLERS, default=1): vol.In(
            {i: str(i) for i in range(1, MAX_CONTROLLERS + 1)}
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


async def _async_validate_connection(host: str, port: int) -> None:
    """Validate the user input allows us to connect."""
    client = RussoundRNETClient(RussoundTcpConnectionHandler(host, port))
    try:
        await client.connect()
    finally:
        await client.disconnect()


class RussoundRNETConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Russound RNET."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            self._async_abort_entries_match(
                {CONF_HOST: host, CONF_PORT: port}
            )
            try:
                await _async_validate_connection(host, port)
            except RNET_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                sources = _sources_from_config(user_input)
                num_controllers = user_input.get(CONF_CONTROLLERS, 1)
                total_zones = num_controllers * ZONES_PER_CONTROLLER
                zones = {str(i): f"Zone {i}" for i in range(1, total_zones + 1)}
                return self.async_create_entry(
                    title=f"{host}:{port}",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_SOURCES: sources,
                        CONF_ZONES: zones,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> ConfigFlowResult:
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={CONF_SOURCES: _sources_from_config(user_input)}
            )

        previous_sources = self._previous_sources()

        options: VolDictType = {
            _key_for_source(idx + 1, source, previous_sources): str
            for idx, source in enumerate(SOURCES)
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options),
        )
