"""Config flow: host/port -> SNMP version + credentials -> test -> discover -> confirm."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_PORT, DOMAIN
from .discovery import UnitMap, unit_map_to_dict
from .enquiry import DeviceInfo, enquire, test_connection
from .options_flow import RittalPduOptionsFlow
from .snmp_client import (
    SnmpClient,
    SnmpError,
    SnmpV1V2Credentials,
    SnmpV3Credentials,
    SnmpVersion,
)

_LOGGER = logging.getLogger(__name__)

CONF_VERSION = "snmp_version"
CONF_READ_COMMUNITY = "read_community"
CONF_WRITE_COMMUNITY = "write_community"
CONF_USERNAME = "username"
CONF_AUTH_KEY = "auth_key"
CONF_PRIV_KEY = "priv_key"

_V1V2_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_READ_COMMUNITY, default="public"): str,
        vol.Optional(CONF_WRITE_COMMUNITY, default=""): str,
    }
)
_V3_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Optional(CONF_AUTH_KEY): str,
        vol.Optional(CONF_PRIV_KEY): str,
    }
)


def build_client(user_input: dict[str, Any]) -> SnmpClient:
    version = SnmpVersion(user_input[CONF_VERSION])
    if version is SnmpVersion.V3:
        credentials: Any = SnmpV3Credentials(
            username=user_input[CONF_USERNAME],
            auth_key=user_input.get(CONF_AUTH_KEY) or None,
            priv_key=user_input.get(CONF_PRIV_KEY) or None,
        )
    else:
        credentials = SnmpV1V2Credentials(
            read_community=user_input[CONF_READ_COMMUNITY],
            write_community=user_input.get(CONF_WRITE_COMMUNITY) or None,
        )
    return SnmpClient(
        host=user_input["host"],
        port=user_input.get("port", DEFAULT_PORT),
        version=version,
        credentials=credentials,
    )


class RittalSnmpPduConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._discovery_summary: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._user_input.update(user_input)
            if user_input[CONF_VERSION] == SnmpVersion.V3.value:
                return await self.async_step_v3_credentials()
            return await self.async_step_v1v2_credentials()

        schema = vol.Schema(
            {
                vol.Required("host"): str,
                vol.Optional("port", default=DEFAULT_PORT): int,
                vol.Required(CONF_VERSION, default=SnmpVersion.V3.value): vol.In(
                    [SnmpVersion.V1.value, SnmpVersion.V2C.value, SnmpVersion.V3.value]
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_v1v2_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._user_input.update(user_input)
            errors = await self._test_and_discover()
            if not errors:
                return await self.async_step_confirm()
            return self.async_show_form(
                step_id="v1v2_credentials", data_schema=_V1V2_SCHEMA, errors=errors
            )
        return self.async_show_form(step_id="v1v2_credentials", data_schema=_V1V2_SCHEMA)

    async def async_step_v3_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._user_input.update(user_input)
            errors = await self._test_and_discover()
            if not errors:
                return await self.async_step_confirm()
            return self.async_show_form(step_id="v3_credentials", data_schema=_V3_SCHEMA, errors=errors)
        return self.async_show_form(step_id="v3_credentials", data_schema=_V3_SCHEMA)

    async def _test_and_discover(self) -> dict[str, str]:
        """Try connecting + enquiring; return an errors dict (empty on success)."""
        client = build_client(self._user_input)
        try:
            await test_connection(client)
            device_info: DeviceInfo
            unit_map: UnitMap
            device_info, unit_map = await enquire(client)
        except SnmpError:
            _LOGGER.exception("Failed to connect to Rittal PDU")
            return {"base": "cannot_connect"}

        self._user_input["unit_map"] = unit_map_to_dict(unit_map)
        self._discovery_summary = {
            "name": device_info.name,
            "outlet_count": len(unit_map.outlets),
            "switchable_outlets": sum(1 for o in unit_map.outlets if o.switch is not None),
            "inlet_sensor_count": len(unit_map.inlet_sensors),
        }
        return {}

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            title = f"Rittal PDU ({self._user_input['host']})"
            return self.async_create_entry(title=title, data=self._user_input)

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovery_summary["name"],
                "outlet_count": str(self._discovery_summary["outlet_count"]),
                "switchable_outlets": str(self._discovery_summary["switchable_outlets"]),
                "inlet_sensor_count": str(self._discovery_summary["inlet_sensor_count"]),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RittalPduOptionsFlow(config_entry)
