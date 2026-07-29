"""SNMP-backed enquiry: fetch the live cmcIIIDevTable/cmcIIIVarTable rows and
hand them to discovery.py's pure classification logic.

Split out from discovery.py so that discovery's grouping/classification
rules stay unit-testable against a static fixture (tests/test_discovery.py)
with no network dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DEV_ALIAS_COL,
    DEV_FW_COL,
    DEV_HW_COL,
    DEV_NAME_COL,
    DEV_SERIAL_COL,
    DEV_TABLE_BASE,
    DEV_TYPE_COL,
    PRODUCT_CHASSIS_BASE,
    UNIT_STATUS_OID,
    VAR_ACCESS_COL,
    VAR_DATA_TYPE_COL,
    VAR_NAME_COL,
    VAR_QUALITY_COL,
    VAR_SCALE_COL,
    VAR_TABLE_BASE,
    VAR_TYPE_COL,
    VAR_UNIT_COL,
)
from .discovery import RawVar, UnitMap, build_unit_map
from .snmp_client import SnmpClient, SnmpError


@dataclass(frozen=True)
class DeviceInfo:
    """Identity of the single cmcIIIDevTable row backing the whole PDU."""

    device_index: int
    name: str
    alias: str
    serial: str
    firmware: str
    hardware: str
    chassis_oid: tuple[int, ...] | None


async def test_connection(client: SnmpClient) -> None:
    """Raise SnmpError if the unit isn't reachable / credentials are wrong."""
    await client.get(UNIT_STATUS_OID)


async def fetch_device_info(client: SnmpClient, device_index: int = 1) -> DeviceInfo:
    """GET the device row's identity columns (name/alias/type/serial/FW/HW)."""
    values = await client.get_many(
        [
            DEV_TABLE_BASE + (DEV_NAME_COL, device_index),
            DEV_TABLE_BASE + (DEV_ALIAS_COL, device_index),
            DEV_TABLE_BASE + (DEV_TYPE_COL, device_index),
            DEV_TABLE_BASE + (DEV_SERIAL_COL, device_index),
            DEV_TABLE_BASE + (DEV_FW_COL, device_index),
            DEV_TABLE_BASE + (DEV_HW_COL, device_index),
        ]
    )
    chassis_value = values.get(DEV_TABLE_BASE + (DEV_TYPE_COL, device_index))
    chassis_oid: tuple[int, ...] | None = None
    if chassis_value is not None:
        try:
            chassis_oid = tuple(int(p) for p in chassis_value)
        except (TypeError, ValueError):
            chassis_oid = None

    def _str(col: int) -> str:
        return str(values.get(DEV_TABLE_BASE + (col, device_index), ""))

    return DeviceInfo(
        device_index=device_index,
        name=_str(DEV_NAME_COL),
        alias=_str(DEV_ALIAS_COL),
        serial=_str(DEV_SERIAL_COL),
        firmware=_str(DEV_FW_COL),
        hardware=_str(DEV_HW_COL),
        chassis_oid=chassis_oid,
    )


def chassis_model_suffix(chassis_oid: tuple[int, ...] | None) -> int | None:
    """Return the trailing chassis-code integer (e.g. 14848), if resolvable."""
    if chassis_oid is None or chassis_oid[: len(PRODUCT_CHASSIS_BASE)] != PRODUCT_CHASSIS_BASE:
        return None
    return chassis_oid[len(PRODUCT_CHASSIS_BASE)]


async def fetch_raw_vars(client: SnmpClient, device_index: int = 1) -> list[RawVar]:
    """Walk every column of cmcIIIVarTable for one device, assembled by var index."""
    columns = {
        VAR_NAME_COL: "name",
        VAR_TYPE_COL: "var_type",
        VAR_UNIT_COL: "unit",
        VAR_DATA_TYPE_COL: "data_type",
        VAR_SCALE_COL: "scale",
        VAR_ACCESS_COL: "access",
        VAR_QUALITY_COL: "quality",
    }

    per_index: dict[int, dict[str, object]] = {}
    for col, field_name in columns.items():
        prefix = VAR_TABLE_BASE + (col, device_index)
        try:
            walked = await client.walk_column(prefix)
        except SnmpError:
            continue
        for oid, value in walked.items():
            var_index = oid[-1]
            per_index.setdefault(var_index, {})[field_name] = value

    raw_vars: list[RawVar] = []
    for var_index, fields in per_index.items():
        if "name" not in fields:
            continue
        raw_vars.append(
            RawVar(
                var_index=var_index,
                name=str(fields["name"]),
                var_type=int(fields.get("var_type", 0)),
                unit=str(fields.get("unit", "")),
                data_type=int(fields.get("data_type", 0)),
                scale=int(fields.get("scale", 0)),
                access=int(fields.get("access", 0)),
                quality=int(fields.get("quality", 2)),
            )
        )
    return raw_vars


async def enquire(client: SnmpClient, device_index: int = 1) -> tuple[DeviceInfo, UnitMap]:
    """Full enquiry pass: device identity + classified unit map."""
    device_info = await fetch_device_info(client, device_index)
    raw_vars = await fetch_raw_vars(client, device_index)
    return device_info, build_unit_map(raw_vars)
