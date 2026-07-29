"""Parse a raw `snmpwalk -Ov` text dump of cmcIIIVarTable into RawVar rows.

Used only to build test fixtures from real captures such as
tests/fixtures/dk7955_401_snmpwalk.txt -- not part of the runtime integration.
"""
from __future__ import annotations

import re
from pathlib import Path

from custom_components.rittal_snmp_pdu.const import (
    VAR_ACCESS_COL,
    VAR_DATA_TYPE_COL,
    VAR_NAME_COL,
    VAR_QUALITY_COL,
    VAR_SCALE_COL,
    VAR_TYPE_COL,
    VAR_UNIT_COL,
)
from custom_components.rittal_snmp_pdu.discovery import RawVar

_LINE_RE = re.compile(
    r"^SNMPv2-SMI::enterprises\.2606\.7\.4\.2\.2\.1\.(?P<col>\d+)\.(?P<dev>\d+)\.(?P<idx>\d+)"
    r"\s*=\s*(?:STRING:\s*\"(?P<str>.*)\"|INTEGER:\s*(?P<int>-?\d+)|Gauge32:\s*(?P<gauge>-?\d+))\s*$"
)


def parse_var_table(path: Path, device_index: int = 1) -> list[RawVar]:
    per_index: dict[int, dict[int, str | int]] = {}
    for line in path.read_text().splitlines():
        match = _LINE_RE.match(line)
        if not match or int(match.group("dev")) != device_index:
            continue
        col = int(match.group("col"))
        idx = int(match.group("idx"))
        if match.group("str") is not None:
            value: str | int = match.group("str")
        else:
            value = int(match.group("int") or match.group("gauge"))
        per_index.setdefault(idx, {})[col] = value

    raw_vars: list[RawVar] = []
    for idx, cols in per_index.items():
        if VAR_NAME_COL not in cols:
            continue
        raw_vars.append(
            RawVar(
                var_index=idx,
                name=str(cols[VAR_NAME_COL]),
                var_type=int(cols.get(VAR_TYPE_COL, 0)),
                unit=str(cols.get(VAR_UNIT_COL, "")),
                data_type=int(cols.get(VAR_DATA_TYPE_COL, 0)),
                scale=int(cols.get(VAR_SCALE_COL, 0)),
                access=int(cols.get(VAR_ACCESS_COL, 0)),
                quality=int(cols.get(VAR_QUALITY_COL, 2)),
            )
        )
    return raw_vars
