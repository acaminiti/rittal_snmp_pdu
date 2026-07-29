"""Tests for the switch/sensor entities, driven by a real RittalPduCoordinator
backed by FakeSnmpClient -- exercises the full fake-network -> coordinator ->
entity data flow, not just each piece in isolation.
"""
from dataclasses import dataclass

from custom_components.rittal_snmp_pdu.const import VAR_TABLE_BASE, VAR_VALUE_INT_COL
from custom_components.rittal_snmp_pdu.coordinator import RittalPduCoordinator
from custom_components.rittal_snmp_pdu.discovery import all_var_indices, build_unit_map
from custom_components.rittal_snmp_pdu.entity import outlet_device_info
from custom_components.rittal_snmp_pdu.sensor import OutletStatusTextSensor, VarValueSensor
from custom_components.rittal_snmp_pdu.switch import OutletSwitch
from tests.fakes import FakeSnmpClient
from tests.helpers import parse_var_table
from tests.test_discovery import FIXTURE

pytest_plugins = "pytest_homeassistant_custom_component"


@dataclass
class _FakeConfigEntry:
    entry_id: str = "test_entry"
    title: str = "Test PDU"


async def _refreshed_coordinator(hass, client) -> tuple[RittalPduCoordinator, object]:
    unit_map = build_unit_map(parse_var_table(FIXTURE))
    var_indices = all_var_indices(unit_map)
    entry = _FakeConfigEntry()
    coordinator = RittalPduCoordinator(
        hass, entry, client, device_index=1, var_indices=var_indices, scan_interval=30
    )
    await coordinator.async_refresh()
    return coordinator, unit_map


async def test_switch_is_on_reflects_relay_value(hass):
    client = FakeSnmpClient()
    coordinator, unit_map = await _refreshed_coordinator(hass, client)
    entry = _FakeConfigEntry()
    socket_01 = unit_map.outlets[0]

    relay_oid = VAR_TABLE_BASE + (VAR_VALUE_INT_COL, 1, socket_01.switch.relay_var_index)
    client.oids[relay_oid] = 0
    await coordinator.async_refresh()
    entity = OutletSwitch(coordinator, entry, socket_01.socket_number, socket_01.name, socket_01.switch)
    assert entity.is_on is False

    client.oids[relay_oid] = 1
    await coordinator.async_refresh()
    assert entity.is_on is True


async def test_switch_unavailable_when_var_missing(hass):
    client = FakeSnmpClient()
    coordinator, unit_map = await _refreshed_coordinator(hass, client)
    entry = _FakeConfigEntry()
    socket_01 = unit_map.outlets[0]
    entity = OutletSwitch(coordinator, entry, socket_01.socket_number, socket_01.name, socket_01.switch)

    coordinator.data.pop(socket_01.switch.relay_var_index)
    assert entity.available is False


async def test_switch_turn_on_and_off_write_through_coordinator(hass):
    client = FakeSnmpClient()
    coordinator, unit_map = await _refreshed_coordinator(hass, client)
    entry = _FakeConfigEntry()
    socket_01 = unit_map.outlets[0]
    relay_oid = VAR_TABLE_BASE + (VAR_VALUE_INT_COL, 1, socket_01.switch.relay_var_index)
    entity = OutletSwitch(coordinator, entry, socket_01.socket_number, socket_01.name, socket_01.switch)

    try:
        # async_turn_on/off write through the coordinator's debounced
        # async_request_refresh -- force an immediate (non-debounced)
        # async_refresh() afterward so the test doesn't depend on the
        # debouncer's real-time cooldown to observe the resulting state.
        await entity.async_turn_on()
        await coordinator.async_refresh()
        assert (relay_oid, 1) in client.set_calls
        assert entity.is_on is True

        await entity.async_turn_off()
        await coordinator.async_refresh()
        assert (relay_oid, 0) in client.set_calls
        assert entity.is_on is False
    finally:
        coordinator._debounced_refresh.async_shutdown()


async def test_sensor_native_value_applies_scale(hass):
    client = FakeSnmpClient()
    coordinator, unit_map = await _refreshed_coordinator(hass, client)
    entry = _FakeConfigEntry()
    socket_01 = unit_map.outlets[0]
    current_sensor_descriptor = next(s for s in socket_01.sensors if s.key == "Current.Value")

    current_oid = VAR_TABLE_BASE + (VAR_VALUE_INT_COL, 1, current_sensor_descriptor.var_index)
    client.oids[current_oid] = 150  # raw, scale -100 -> divide by 100
    await coordinator.async_refresh()

    device_info = outlet_device_info(entry, socket_01.socket_number, socket_01.name)
    entity = VarValueSensor(coordinator, device_info, entry, current_sensor_descriptor, "socket_1")

    assert entity.native_value == 1.5


async def test_sensor_unavailable_when_var_missing(hass):
    client = FakeSnmpClient()
    coordinator, unit_map = await _refreshed_coordinator(hass, client)
    entry = _FakeConfigEntry()
    socket_01 = unit_map.outlets[0]
    descriptor = socket_01.sensors[0]
    device_info = outlet_device_info(entry, socket_01.socket_number, socket_01.name)
    entity = VarValueSensor(coordinator, device_info, entry, descriptor, "socket_1")

    coordinator.data.pop(descriptor.var_index)
    assert entity.available is False
    assert entity.native_value is None


async def test_outlet_status_text_sensor_reads_value_str(hass):
    client = FakeSnmpClient()
    coordinator, unit_map = await _refreshed_coordinator(hass, client)
    entry = _FakeConfigEntry()
    socket_01 = unit_map.outlets[0]
    device_info = outlet_device_info(entry, socket_01.socket_number, socket_01.name)
    entity = OutletStatusTextSensor(
        coordinator, device_info, entry, socket_01.socket_number, socket_01.switch.status_var_index
    )

    sample = coordinator.data[socket_01.switch.status_var_index]
    assert entity.native_value == sample.value_str
