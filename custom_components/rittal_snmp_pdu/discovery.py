"""Enquiry logic: turn a raw cmcIIIVarTable walk into a structured unit map.

The Rittal CMC III agent exposes one flat table of variables per physical
unit (see const.py for the OID layout). Every variable's name is a
dot-hierarchical path, e.g.:

    Unit.Power.Active.Value
    Phase L1.Voltage.Value
    Sockets.Socket 01.General.Relay
    Memory.USB-Stick.Status

Discovery groups variables by their top-level path segment(s) and classifies
each leaf using only generic MIB fields (VarType/DataType/Access/Unit) --
never literal per-model strings -- so it generalizes across any Rittal PDU
built on this agent (metered-only, switched-only, or managed; single- or
multi-phase; any outlet count).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .const import (
    ENERGY_CUSTOM_MARKER,
    SOCKET_RELAY_LEAF,
    SOCKET_STATUS_LEAF,
    SOCKETS_GROUP,
    VarAccess,
    VarDataType,
    VarQuality,
    VarType,
    WRITABLE_ACCESS,
)

_SOCKET_NAME_RE = re.compile(r"^Socket\s+(\d+)$")
_PHASE_NAME_RE = re.compile(r"^Phase\s+(L\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class RawVar:
    """One row of cmcIIIVarTable, as read off the wire."""

    var_index: int
    name: str
    var_type: int
    unit: str
    data_type: int
    scale: int
    access: int
    quality: int = VarQuality.OK


@dataclass(frozen=True)
class SensorDescriptor:
    """One classified `value`-type var, ready to become a sensor entity."""

    var_index: int
    key: str  # unique leaf key, e.g. "Current.Value" or "Power.Active.Value"
    unit: str
    scale: int
    is_energy_resettable: bool = False


@dataclass(frozen=True)
class SwitchDescriptor:
    """An outlet's relay control (write) paired with its status feedback (read).

    See switch.py for why both exist: the relay var is used for both
    control and on/off state; status is exposed as a diagnostic sensor.
    """

    relay_var_index: int  # writable var (General.Relay)
    status_var_index: int  # read-only feedback var (General.Status)


@dataclass(frozen=True)
class OutletGroup:
    """Everything discovered under one `Sockets.Socket NN` group."""

    socket_number: int
    name: str  # e.g. "Socket 01"
    switch: SwitchDescriptor | None
    sensors: list[SensorDescriptor] = field(default_factory=list)


@dataclass(frozen=True)
class UnitMap:
    """Full result of an enquiry pass, ready to persist in a config entry."""

    root_sensors: list[SensorDescriptor]  # everything NOT under Sockets/Phase L<n>
    inlet_sensors: list[SensorDescriptor]  # merged from all Phase L<n> groups
    outlets: list[OutletGroup]


def _split_top_group(name: str) -> tuple[str, str]:
    """Split "Sockets.Socket 01.General.Relay" -> ("Sockets.Socket 01", "General.Relay").

    For everything else, only the first dot-segment is the group, e.g.
    "Unit.Power.Active.Value" -> ("Unit", "Power.Active.Value").
    """
    parts = name.split(".")
    if parts[0] == SOCKETS_GROUP and len(parts) > 2:
        return f"{parts[0]}.{parts[1]}", ".".join(parts[2:])
    return parts[0], ".".join(parts[1:])


def _is_value_leaf(var: RawVar) -> bool:
    """Whether a var is a plain numeric reading (candidate sensor)."""
    return var.var_type == VarType.VALUE and var.data_type == VarDataType.INT


def _build_sensor(var: RawVar, leaf: str) -> SensorDescriptor:
    """Wrap one value-type var as a SensorDescriptor."""
    return SensorDescriptor(
        var_index=var.var_index,
        key=leaf,
        unit=var.unit,
        scale=var.scale,
        is_energy_resettable=ENERGY_CUSTOM_MARKER in leaf,
    )


def _build_outlet(group_name: str, leaves: dict[str, RawVar]) -> OutletGroup:
    """Classify one `Sockets.Socket NN` group's leaves into a switch + sensors."""
    match = _SOCKET_NAME_RE.match(group_name.split(".", 1)[1])
    socket_number = int(match.group(1)) if match else 0

    switch: SwitchDescriptor | None = None
    relay = leaves.get(SOCKET_RELAY_LEAF)
    status = leaves.get(SOCKET_STATUS_LEAF)
    if (
        relay is not None
        and status is not None
        and relay.var_type == VarType.OUTPUT
        and VarAccess(relay.access) in WRITABLE_ACCESS
    ):
        switch = SwitchDescriptor(relay_var_index=relay.var_index, status_var_index=status.var_index)

    sensors = [_build_sensor(var, leaf) for leaf, var in leaves.items() if _is_value_leaf(var)]

    return OutletGroup(
        socket_number=socket_number,
        name=group_name.split(".", 1)[1],
        switch=switch,
        sensors=sensors,
    )


def build_unit_map(raw_vars: list[RawVar]) -> UnitMap:
    """Group + classify a full cmcIIIVarTable walk for one device row."""
    groups: dict[str, dict[str, RawVar]] = {}
    for var in raw_vars:
        group, leaf = _split_top_group(var.name)
        groups.setdefault(group, {})[leaf] = var

    root_sensors: list[SensorDescriptor] = []
    inlet_sensors: list[SensorDescriptor] = []
    outlets: list[OutletGroup] = []

    for group_name, leaves in groups.items():
        phase_match = _PHASE_NAME_RE.match(group_name)
        if group_name.startswith(f"{SOCKETS_GROUP}."):
            outlets.append(_build_outlet(group_name, leaves))
        elif phase_match:
            phase = phase_match.group(1).upper()
            for leaf, var in leaves.items():
                if _is_value_leaf(var):
                    inlet_sensors.append(_build_sensor(var, f"{phase}.{leaf}"))
        else:
            for leaf, var in leaves.items():
                if _is_value_leaf(var):
                    root_sensors.append(_build_sensor(var, f"{group_name}.{leaf}"))

    outlets.sort(key=lambda o: o.socket_number)
    return UnitMap(root_sensors=root_sensors, inlet_sensors=inlet_sensors, outlets=outlets)


def all_var_indices(unit_map: UnitMap) -> list[int]:
    """Every var index the coordinator needs to poll."""
    indices = {s.var_index for s in unit_map.root_sensors}
    indices |= {s.var_index for s in unit_map.inlet_sensors}
    for outlet in unit_map.outlets:
        indices |= {s.var_index for s in outlet.sensors}
        if outlet.switch is not None:
            indices.add(outlet.switch.relay_var_index)
            indices.add(outlet.switch.status_var_index)
    return sorted(indices)


def _sensor_to_dict(sensor: SensorDescriptor) -> dict:
    """SensorDescriptor -> plain dict (paired with _sensor_from_dict)."""
    return {
        "var_index": sensor.var_index,
        "key": sensor.key,
        "unit": sensor.unit,
        "scale": sensor.scale,
        "is_energy_resettable": sensor.is_energy_resettable,
    }


def _sensor_from_dict(data: dict) -> SensorDescriptor:
    """Inverse of _sensor_to_dict."""
    return SensorDescriptor(
        var_index=data["var_index"],
        key=data["key"],
        unit=data["unit"],
        scale=data["scale"],
        is_energy_resettable=data["is_energy_resettable"],
    )


def unit_map_to_dict(unit_map: UnitMap) -> dict:
    """JSON-serializable form, for storing in a config entry."""
    return {
        "root_sensors": [_sensor_to_dict(s) for s in unit_map.root_sensors],
        "inlet_sensors": [_sensor_to_dict(s) for s in unit_map.inlet_sensors],
        "outlets": [
            {
                "socket_number": o.socket_number,
                "name": o.name,
                "switch": (
                    {
                        "relay_var_index": o.switch.relay_var_index,
                        "status_var_index": o.switch.status_var_index,
                    }
                    if o.switch is not None
                    else None
                ),
                "sensors": [_sensor_to_dict(s) for s in o.sensors],
            }
            for o in unit_map.outlets
        ],
    }


def unit_map_from_dict(data: dict) -> UnitMap:
    """Inverse of unit_map_to_dict -- reconstructs a UnitMap from config entry data."""
    return UnitMap(
        root_sensors=[_sensor_from_dict(s) for s in data["root_sensors"]],
        inlet_sensors=[_sensor_from_dict(s) for s in data["inlet_sensors"]],
        outlets=[
            OutletGroup(
                socket_number=o["socket_number"],
                name=o["name"],
                switch=(SwitchDescriptor(**o["switch"]) if o["switch"] is not None else None),
                sensors=[_sensor_from_dict(s) for s in o["sensors"]],
            )
            for o in data["outlets"]
        ],
    )
