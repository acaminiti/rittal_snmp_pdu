"""Options: polling interval, plus a "rediscover" action that re-runs the
enquiry walk and reloads the entry (for outlet/model changes post-setup)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .discovery import unit_map_to_dict
from .enquiry import enquire, test_connection
from .snmp_client import SnmpError

_LOGGER = logging.getLogger(__name__)

REDISCOVER_ACTION = "rediscover"


class RittalPduOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(REDISCOVER_ACTION):
                return await self._rediscover(errors)
            return self.async_create_entry(
                title="", data={CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]}
            )

        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): int,
                vol.Optional(REDISCOVER_ACTION, default=False): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def _rediscover(self, errors: dict[str, str]) -> FlowResult:
        runtime = self._config_entry.runtime_data
        try:
            await test_connection(runtime.client)
            _device_info, unit_map = await enquire(runtime.client)
        except SnmpError:
            _LOGGER.exception("Rediscovery failed")
            errors["base"] = "cannot_connect"
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): int,
                    vol.Optional(REDISCOVER_ACTION, default=False): bool,
                }
            )
            return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

        # async_update_entry fires the update listener registered in __init__.py,
        # which reloads the entry -- no need to reload explicitly here too.
        new_data = {**self._config_entry.data, "unit_map": unit_map_to_dict(unit_map)}
        self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
        return self.async_create_entry(title="", data={**self._config_entry.options})
