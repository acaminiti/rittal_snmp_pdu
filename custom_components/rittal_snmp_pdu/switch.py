"""Outlet on/off control.

`General.Relay` is read-write: writing 0/1 switches the outlet, and reading
it back reflects the actual relay position (confirmed on a live DK 7955.401:
ValueInt=0/ValueStr="Off" when off) -- so it's used for both control and
state. The companion read-only `General.Status` var uses a separate enum
encoding (e.g. ValueInt=10 for "Off") and is exposed as a diagnostic text
sensor instead (see sensor.py), not used for on/off state.
"""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RittalPduEntity, outlet_device_info
from .runtime import RittalPduRuntimeData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: RittalPduRuntimeData = entry.runtime_data
    entities = [
        OutletSwitch(runtime.coordinator, entry, outlet.socket_number, outlet.name, outlet.switch)
        for outlet in runtime.unit_map.outlets
        if outlet.switch is not None
    ]
    async_add_entities(entities)


class OutletSwitch(RittalPduEntity, SwitchEntity):
    _attr_name = None  # outlet device name doubles as the entity name

    def __init__(self, coordinator, entry: ConfigEntry, socket_number: int, name: str, switch) -> None:
        super().__init__(
            coordinator,
            outlet_device_info(entry, socket_number, name),
            f"{entry.entry_id}_socket_{socket_number}_switch",
        )
        self._relay_var_index = switch.relay_var_index
        self._status_var_index = switch.status_var_index

    @property
    def is_on(self) -> bool | None:
        sample = self.coordinator.data.get(self._relay_var_index)
        return bool(sample.value_int) if sample is not None else None

    @property
    def available(self) -> bool:
        return super().available and self._relay_var_index in self.coordinator.data

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write_var(self._relay_var_index, 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write_var(self._relay_var_index, 0)
