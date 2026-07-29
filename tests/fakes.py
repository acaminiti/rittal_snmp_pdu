"""Test doubles.

FakeSnmpClient implements the same async interface as
custom_components.rittal_snmp_pdu.snmp_client.SnmpClient, backed by an
in-memory OID->value dict, so coordinator/entity/config_flow tests can
run without any real network access. Seeded from the same real capture
(tests/fixtures/dk7955_401_snmpwalk.txt) that test_discovery.py uses, so
"live-shaped" data is exercised throughout the test suite, not just in
discovery tests.
"""
from __future__ import annotations

from pathlib import Path

from custom_components.rittal_snmp_pdu.const import (
    DEV_ALIAS_COL,
    DEV_FW_COL,
    DEV_HW_COL,
    DEV_NAME_COL,
    DEV_SERIAL_COL,
    DEV_TABLE_BASE,
    DEV_TYPE_COL,
    UNIT_STATUS_OID,
    VAR_TABLE_BASE,
)
from custom_components.rittal_snmp_pdu.snmp_client import Oid, SnmpError
from tests.helpers import _LINE_RE

FIXTURE = Path(__file__).parent / "fixtures" / "dk7955_401_snmpwalk.txt"

# Real values read back from the DK 7955.401 during live testing (see
# project memory / conversation history) -- not present in the raw
# snmpwalk capture's device-table rows in a form the regex-based fixture
# parser reuses, so seeded directly here.
_DEVICE_ROW = {
    DEV_TABLE_BASE + (DEV_NAME_COL, 1): "PDU-MAN",
    DEV_TABLE_BASE + (DEV_ALIAS_COL, 1): "PDU",
    DEV_TABLE_BASE + (DEV_TYPE_COL, 1): (1, 3, 6, 1, 4, 1, 2606, 7, 7, 4, 14848),
    DEV_TABLE_BASE + (DEV_SERIAL_COL, 1): "12600347",
    DEV_TABLE_BASE + (DEV_FW_COL, 1): "V5.15.50_11",
    DEV_TABLE_BASE + (DEV_HW_COL, 1): "V2.00",
}


def load_fixture_oids(device_index: int = 1) -> dict[Oid, object]:
    """Every cmcIIIVarTable cell from the real capture, keyed by full OID."""
    oids: dict[Oid, object] = dict(_DEVICE_ROW)
    oids[UNIT_STATUS_OID] = 2  # ok
    for line in FIXTURE.read_text().splitlines():
        match = _LINE_RE.match(line)
        if not match or int(match.group("dev")) != device_index:
            continue
        col = int(match.group("col"))
        idx = int(match.group("idx"))
        if match.group("str") is not None:
            value: object = match.group("str")
        else:
            value = int(match.group("int") or match.group("gauge"))
        oids[VAR_TABLE_BASE + (col, device_index, idx)] = value
    return oids


class FakeSnmpClient:
    """Drop-in stand-in for SnmpClient, backed by an in-memory OID map."""

    def __init__(self, oids: dict[Oid, object] | None = None) -> None:
        self.oids: dict[Oid, object] = oids if oids is not None else load_fixture_oids()
        self.set_calls: list[tuple[Oid, int]] = []
        self.raise_on_write: SnmpError | None = None

    async def get(self, oid: Oid) -> object:
        if oid not in self.oids:
            raise SnmpError(f"no such OID in fake data: {oid}")
        return self.oids[oid]

    async def get_many(self, oids: list[Oid]) -> dict[Oid, object]:
        return {oid: self.oids[oid] for oid in oids if oid in self.oids}

    async def get_bulk_many(self, oids: list[Oid]) -> dict[Oid, object]:
        return await self.get_many(oids)

    async def walk_column(self, prefix: Oid) -> dict[Oid, object]:
        return {oid: value for oid, value in self.oids.items() if oid[: len(prefix)] == prefix}

    async def set(self, oid: Oid, value: int) -> None:
        if self.raise_on_write is not None:
            raise self.raise_on_write
        self.set_calls.append((oid, value))
        self.oids[oid] = value
