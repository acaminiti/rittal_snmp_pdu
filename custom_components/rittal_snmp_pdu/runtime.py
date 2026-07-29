"""Per-config-entry runtime state, stored at entry.runtime_data."""
from __future__ import annotations

from dataclasses import dataclass

from .coordinator import RittalPduCoordinator
from .discovery import UnitMap
from .enquiry import DeviceInfo
from .snmp_client import SnmpClient


@dataclass
class RittalPduRuntimeData:
    client: SnmpClient
    coordinator: RittalPduCoordinator
    device_info: DeviceInfo
    unit_map: UnitMap
