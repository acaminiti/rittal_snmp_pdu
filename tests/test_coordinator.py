"""Tests for RittalPduCoordinator against a fake SNMP client (no network)."""
from unittest.mock import MagicMock

from custom_components.rittal_snmp_pdu.coordinator import RittalPduCoordinator
from custom_components.rittal_snmp_pdu.const import VAR_TABLE_BASE, VAR_VALUE_INT_COL
from custom_components.rittal_snmp_pdu.discovery import all_var_indices, build_unit_map
from tests.fakes import FakeSnmpClient
from tests.helpers import parse_var_table
from tests.test_discovery import FIXTURE

pytest_plugins = "pytest_homeassistant_custom_component"


def _make_coordinator(hass, client, var_indices) -> RittalPduCoordinator:
    entry = MagicMock()
    entry.title = "Test PDU"
    return RittalPduCoordinator(hass, entry, client, device_index=1, var_indices=var_indices, scan_interval=30)


async def test_first_refresh_populates_data_for_every_var(hass):
    unit_map = build_unit_map(parse_var_table(FIXTURE))
    var_indices = all_var_indices(unit_map)
    client = FakeSnmpClient()

    coordinator = _make_coordinator(hass, client, var_indices)
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert set(coordinator.data.keys()) == set(var_indices)


async def test_data_reflects_real_relay_value_and_scale(hass):
    unit_map = build_unit_map(parse_var_table(FIXTURE))
    var_indices = all_var_indices(unit_map)
    client = FakeSnmpClient()

    socket_01 = unit_map.outlets[0]
    relay_oid = VAR_TABLE_BASE + (VAR_VALUE_INT_COL, 1, socket_01.switch.relay_var_index)
    client.oids[relay_oid] = 1  # force "on" for this test, independent of the fixture's snapshot

    coordinator = _make_coordinator(hass, client, var_indices)
    await coordinator.async_refresh()

    sample = coordinator.data[socket_01.switch.relay_var_index]
    assert sample.value_int == 1


async def test_write_var_updates_device_and_triggers_refresh(hass):
    unit_map = build_unit_map(parse_var_table(FIXTURE))
    var_indices = all_var_indices(unit_map)
    client = FakeSnmpClient()
    socket_01 = unit_map.outlets[0]
    relay_var_index = socket_01.switch.relay_var_index
    relay_oid = VAR_TABLE_BASE + (VAR_VALUE_INT_COL, 1, relay_var_index)

    coordinator = _make_coordinator(hass, client, var_indices)
    await coordinator.async_refresh()
    assert coordinator.data[relay_var_index].value_int == 0

    try:
        await coordinator.async_write_var(relay_var_index, 1)
        await hass.async_block_till_done()  # let the coordinator's debounced refresh settle

        assert (relay_oid, 1) in client.set_calls
        assert coordinator.data[relay_var_index].value_int == 1  # refreshed after the write
    finally:
        # async_write_var uses the debounced async_request_refresh (same as real
        # usage), which leaves a cooldown timer scheduled; real HA cancels this via
        # async_unload_entry -> coordinator shutdown, which doesn't happen in this
        # standalone test, so shut it down explicitly to avoid a lingering timer.
        coordinator._debounced_refresh.async_shutdown()


async def test_update_failure_surfaces_as_update_failed(hass):
    from custom_components.rittal_snmp_pdu.snmp_client import SnmpError

    unit_map = build_unit_map(parse_var_table(FIXTURE))
    var_indices = all_var_indices(unit_map)
    client = FakeSnmpClient()
    client.raise_on_write = SnmpError("simulated failure")

    async def failing_get_bulk_many(oids):
        raise SnmpError("simulated poll failure")

    client.get_bulk_many = failing_get_bulk_many  # type: ignore[method-assign]

    coordinator = _make_coordinator(hass, client, var_indices)
    await coordinator.async_refresh()

    assert not coordinator.last_update_success
