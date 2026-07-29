"""The Rittal SNMP PDU integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .config_flow import build_client
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import RittalPduCoordinator
from .discovery import all_var_indices, unit_map_from_dict
from .enquiry import fetch_device_info
from .runtime import RittalPduRuntimeData

PLATFORMS = ["switch", "sensor"]

type RittalPduConfigEntry = ConfigEntry[RittalPduRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: RittalPduConfigEntry) -> bool:
    client = build_client(entry.data)
    device_info = await fetch_device_info(client)
    unit_map = unit_map_from_dict(entry.data["unit_map"])
    var_indices = all_var_indices(unit_map)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = RittalPduCoordinator(hass, entry, client, 1, var_indices, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RittalPduRuntimeData(
        client=client, coordinator=coordinator, device_info=device_info, unit_map=unit_map
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: RittalPduConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RittalPduConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
