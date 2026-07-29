"""Base entity + device_info helpers for the real PDU device and the two
kinds of virtual child device (single "Inlet", one per outlet)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .chassis import CHASSIS_MODEL_NAMES
from .const import DOMAIN
from .coordinator import RittalPduCoordinator
from .enquiry import DeviceInfo as PduDeviceInfo, chassis_model_suffix


def _model_name(device_info: PduDeviceInfo) -> str:
    code = chassis_model_suffix(device_info.chassis_oid)
    if code is not None and code in CHASSIS_MODEL_NAMES:
        return CHASSIS_MODEL_NAMES[code]
    return device_info.name or "Rittal PDU"


def root_device_info(entry: ConfigEntry, device_info: PduDeviceInfo) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=device_info.alias or device_info.name or entry.title,
        manufacturer="Rittal",
        model=_model_name(device_info),
        sw_version=device_info.firmware or None,
        hw_version=device_info.hardware or None,
        serial_number=device_info.serial or None,
    )


def inlet_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_inlet")},
        name="Inlet",
        manufacturer="Rittal",
        via_device=(DOMAIN, entry.entry_id),
    )


def outlet_device_info(entry: ConfigEntry, socket_number: int, name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_socket_{socket_number}")},
        name=name,
        manufacturer="Rittal",
        via_device=(DOMAIN, entry.entry_id),
    )


class RittalPduEntity(CoordinatorEntity[RittalPduCoordinator]):
    """Common plumbing: unique_id + device_info for one HA device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RittalPduCoordinator,
        device_info: DeviceInfo,
        unique_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_unique_id = unique_id
