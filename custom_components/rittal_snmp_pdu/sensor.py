"""Unit/inlet/outlet sensors, built purely from what discovery classified.

No per-model hardcoding: device_class/state_class are derived from the
generic cmcIIIVarUnit string (and the energy-resettable flag), so any
value-type var discovery finds -- on any Rittal CMC III PDU -- gets a
sensible HA representation automatically.
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .discovery import SensorDescriptor
from .entity import RittalPduEntity, inlet_device_info, outlet_device_info, root_device_info
from .runtime import RittalPduRuntimeData

_UNIT_DEVICE_CLASS = {
    "A": SensorDeviceClass.CURRENT,
    "V": SensorDeviceClass.VOLTAGE,
    "W": SensorDeviceClass.POWER,
    "kWh": SensorDeviceClass.ENERGY,
    "Hz": SensorDeviceClass.FREQUENCY,
    "GB": SensorDeviceClass.DATA_SIZE,
}


def _apply_scale(raw: int, scale: int) -> float:
    if scale > 0:
        return raw * scale
    if scale < 0:
        return raw / abs(scale)
    return float(raw)


def _describe(descriptor: SensorDescriptor) -> SensorEntityDescription:
    device_class = _UNIT_DEVICE_CLASS.get(descriptor.unit)
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    if device_class is SensorDeviceClass.ENERGY:
        state_class = (
            SensorStateClass.TOTAL if descriptor.is_energy_resettable else SensorStateClass.TOTAL_INCREASING
        )
    name = descriptor.key.replace(".Value", "").replace(".", " ")
    return SensorEntityDescription(
        key=descriptor.key,
        name=name,
        device_class=device_class,
        state_class=state_class,
        native_unit_of_measurement=descriptor.unit or None,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: RittalPduRuntimeData = entry.runtime_data
    unit_map = runtime.unit_map

    entities: list[RittalPduEntity] = [
        VarValueSensor(runtime.coordinator, root_device_info(entry, runtime.device_info), entry, s, "root")
        for s in unit_map.root_sensors
    ]
    entities += [
        VarValueSensor(runtime.coordinator, inlet_device_info(entry), entry, s, "inlet")
        for s in unit_map.inlet_sensors
    ]
    for outlet in unit_map.outlets:
        device_info = outlet_device_info(entry, outlet.socket_number, outlet.name)
        entities += [
            VarValueSensor(
                runtime.coordinator, device_info, entry, s, f"socket_{outlet.socket_number}"
            )
            for s in outlet.sensors
        ]
        if outlet.switch is not None:
            entities.append(
                OutletStatusTextSensor(
                    runtime.coordinator, device_info, entry, outlet.socket_number, outlet.switch.status_var_index
                )
            )

    async_add_entities(entities)


class VarValueSensor(RittalPduEntity, SensorEntity):
    def __init__(self, coordinator, device_info, entry: ConfigEntry, descriptor: SensorDescriptor, scope: str) -> None:
        self.entity_description = _describe(descriptor)
        super().__init__(
            coordinator,
            device_info,
            f"{entry.entry_id}_{scope}_{descriptor.var_index}",
        )
        self._var_index = descriptor.var_index
        self._scale = descriptor.scale

    @property
    def native_value(self) -> float | None:
        sample = self.coordinator.data.get(self._var_index)
        if sample is None:
            return None
        return round(_apply_scale(sample.value_int, self._scale), 3)

    @property
    def available(self) -> bool:
        return super().available and self._var_index in self.coordinator.data


class OutletStatusTextSensor(RittalPduEntity, SensorEntity):
    """Diagnostic text status from the outlet's read-only General.Status var."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_info, entry: ConfigEntry, socket_number: int, status_var_index: int) -> None:
        self._attr_name = "Status"
        super().__init__(
            coordinator,
            device_info,
            f"{entry.entry_id}_socket_{socket_number}_status",
        )
        self._status_var_index = status_var_index

    @property
    def native_value(self) -> str | None:
        sample = self.coordinator.data.get(self._status_var_index)
        return sample.value_str if sample is not None else None

    @property
    def available(self) -> bool:
        return super().available and self._status_var_index in self.coordinator.data
