from pathlib import Path

import pytest

from custom_components.rittal_snmp_pdu.discovery import (
    all_var_indices,
    build_unit_map,
    unit_map_from_dict,
    unit_map_to_dict,
)
from tests.helpers import parse_var_table

FIXTURE = Path(__file__).parent / "fixtures" / "dk7955_401_snmpwalk.txt"


@pytest.fixture(scope="module")
def unit_map():
    raw_vars = parse_var_table(FIXTURE)
    assert len(raw_vars) == 426  # cmcIIINumberOfVars on the real unit
    return build_unit_map(raw_vars)


def test_discovers_all_twelve_outlets(unit_map):
    assert [o.socket_number for o in unit_map.outlets] == list(range(1, 13))


def test_outlet_has_switch_control(unit_map):
    socket_01 = unit_map.outlets[0]
    assert socket_01.name == "Socket 01"
    assert socket_01.switch is not None
    assert socket_01.switch.relay_var_index == 52
    assert socket_01.switch.status_var_index == 54


def test_outlet_sensor_oids_and_scale(unit_map):
    socket_01 = unit_map.outlets[0]
    by_key = {s.key: s for s in socket_01.sensors}

    assert by_key["Current.Value"].var_index == 57
    assert by_key["Current.Value"].unit == "A"
    assert by_key["Current.Value"].scale == -100  # divide by 100

    assert by_key["Power.Active.Value"].var_index == 67
    assert by_key["Power.Active.Value"].unit == "W"


def test_outlet_energy_counters_distinguish_resettable(unit_map):
    socket_01 = unit_map.outlets[0]
    by_key = {s.key: s for s in socket_01.sensors}

    total = by_key["Energy.Active.Value"]
    resettable = by_key["Energy.Active Custom.Value"]

    assert total.var_index == 77
    assert total.is_energy_resettable is False

    assert resettable.var_index == 78
    assert resettable.is_energy_resettable is True


def test_all_outlets_share_the_31_var_block_layout(unit_map):
    relay_indices = [o.switch.relay_var_index for o in unit_map.outlets if o.switch]
    deltas = [b - a for a, b in zip(relay_indices, relay_indices[1:])]
    assert all(d == 31 for d in deltas)


def test_single_phase_unit_merges_into_one_inlet_group(unit_map):
    by_key = {s.key: s for s in unit_map.inlet_sensors}
    assert "L1.Voltage.Value" in by_key
    assert "L1.Current.Value" in by_key
    # no L2/L3 on this single-phase unit
    assert not any(k.startswith("L2.") or k.startswith("L3.") for k in by_key)


def test_root_sensors_include_unit_and_other_top_level_groups(unit_map):
    keys = {s.key for s in unit_map.root_sensors}
    assert "Unit.Power.Active.Value" in keys
    assert "Unit.Energy.Active.Value" in keys
    # A non-power top-level group (USB stick diagnostics) picked up for free by the
    # same generic "value-type leaf" rule -- no group-specific code needed.
    assert "Memory.USB-Stick.Size" in keys
    assert "Memory.USB-Stick.Usage" in keys


def test_unit_map_survives_json_roundtrip(unit_map):
    restored = unit_map_from_dict(unit_map_to_dict(unit_map))
    assert restored == unit_map


def test_all_var_indices_includes_switch_and_sensor_oids(unit_map):
    indices = all_var_indices(unit_map)
    socket_01 = unit_map.outlets[0]
    assert socket_01.switch.relay_var_index in indices
    assert socket_01.switch.status_var_index in indices
    assert all(s.var_index in indices for s in socket_01.sensors)
    assert all(s.var_index in indices for s in unit_map.root_sensors)
