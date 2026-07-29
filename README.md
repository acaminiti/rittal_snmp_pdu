# Rittal SNMP PDU

A [HACS](https://hacs.xyz/) custom integration for Rittal PDUs built on the
CMC III SNMP agent (the 7955.xxx "PDU Metered/Managed/Switched" family and
7979.xxx "PDUi"), including the DK 7955.401 managed PDU.

## Why not the generic `snmp:` YAML platform?

Home Assistant's built-in `snmp` platform works, but every outlet's OID has
to be listed by hand (see the OID math below) and nothing is discovered
automatically. This integration instead **enquires the PDU itself** at setup
time: it walks the unit's variable table and classifies every outlet,
sensor, and inlet reading it actually finds, using only generic fields
Rittal's own MIB provides (`cmcIIIVarType`, `cmcIIIVarAccess`,
`cmcIIIVarUnit`, ...) -- never hardcoded per-model OIDs. That means:

- Full outlet count and per-outlet switchability/metering capability are
  detected automatically, for any CMC III based Rittal PDU (metered-only,
  switched-only, or managed).
- Multi-phase inlets show all phases under a single "Inlet" device.
- A "Rediscover devices" option re-runs the enquiry if hardware changes.

## How it works

Every CMC III PDU (regardless of outlet count or model) exposes a single
device row (`cmcIIIDevTable`) whose full variable table (`cmcIIIVarTable`)
uses dot-hierarchical names, e.g.:

```
Unit.Power.Active.Value               -> total inlet power (W)
Phase L1.Voltage.Value                -> inlet phase voltage
Sockets.Socket 01.General.Relay       -> outlet switch control
Sockets.Socket 01.General.Status      -> outlet switch feedback
Sockets.Socket 01.Current.Value       -> outlet current (A)
Sockets.Socket 01.Power.Active.Value  -> outlet power (W)
```

`custom_components/rittal_snmp_pdu/discovery.py` groups these by their
top-level path (`Unit`, `Phase L<n>`, `Sockets.Socket <nn>`) and classifies
each leaf from generic MIB metadata alone. `enquiry.py` is the only module
that talks SNMP to build this map; `discovery.py` itself is pure and unit
tested against a real capture in `tests/fixtures/dk7955_401_snmpwalk.txt`.

## Installation (HACS custom repository)

1. HACS -> Integrations -> the "..." menu -> Custom repositories.
2. Add this repo's URL, category "Integration".
3. Install "Rittal SNMP PDU", restart Home Assistant.
4. Settings -> Devices & services -> Add integration -> "Rittal SNMP PDU".
5. Enter the PDU's host and choose an SNMP version (v1/v2c/v3, default v3).

## Development

```
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest tests/
```
