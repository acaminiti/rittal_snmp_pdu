"""Data update coordinator: polls every OID the enquiry pass discovered."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    VAR_QUALITY_COL,
    VAR_TABLE_BASE,
    VAR_VALUE_INT_COL,
    VAR_VALUE_STR_COL,
)
from .snmp_client import SnmpClient, SnmpError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VarSample:
    value_int: int
    value_str: str
    quality: int


class RittalPduCoordinator(DataUpdateCoordinator[dict[int, VarSample]]):
    """Polls value/quality for every known var index of one PDU."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SnmpClient,
        device_index: int,
        var_indices: list[int],
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.title})",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.device_index = device_index
        self.var_indices = var_indices

    async def _async_update_data(self) -> dict[int, VarSample]:
        value_oids = [
            VAR_TABLE_BASE + (VAR_VALUE_INT_COL, self.device_index, idx) for idx in self.var_indices
        ]
        str_oids = [
            VAR_TABLE_BASE + (VAR_VALUE_STR_COL, self.device_index, idx) for idx in self.var_indices
        ]
        quality_oids = [
            VAR_TABLE_BASE + (VAR_QUALITY_COL, self.device_index, idx) for idx in self.var_indices
        ]
        try:
            values = await self.client.get_bulk_many(value_oids)
            strings = await self.client.get_bulk_many(str_oids)
            qualities = await self.client.get_bulk_many(quality_oids)
        except SnmpError as err:
            raise UpdateFailed(f"Error polling Rittal PDU: {err}") from err

        data: dict[int, VarSample] = {}
        for idx in self.var_indices:
            value = values.get(VAR_TABLE_BASE + (VAR_VALUE_INT_COL, self.device_index, idx))
            value_str = strings.get(VAR_TABLE_BASE + (VAR_VALUE_STR_COL, self.device_index, idx))
            quality = qualities.get(VAR_TABLE_BASE + (VAR_QUALITY_COL, self.device_index, idx))
            if value is None:
                continue
            data[idx] = VarSample(
                value_int=int(value),
                value_str=str(value_str) if value_str is not None else "",
                quality=int(quality) if quality is not None else 2,
            )
        return data

    async def async_write_var(self, var_index: int, value: int) -> None:
        """Write an int value to a writable var (e.g. an outlet relay)."""
        oid = VAR_TABLE_BASE + (VAR_VALUE_INT_COL, self.device_index, var_index)
        await self.client.set(oid, value)
        await self.async_request_refresh()
