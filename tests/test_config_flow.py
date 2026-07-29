"""Tests for the config flow: version routing, the happy path (test connection
-> discover -> confirm -> create entry), and the connection-failure error path.
`enquire`/`test_connection` are monkeypatched -- no real network involved.
"""
import custom_components.rittal_snmp_pdu as integration_module
from custom_components.rittal_snmp_pdu import config_flow as config_flow_module
from custom_components.rittal_snmp_pdu.const import DOMAIN
from custom_components.rittal_snmp_pdu.discovery import build_unit_map
from custom_components.rittal_snmp_pdu.enquiry import DeviceInfo
from custom_components.rittal_snmp_pdu.snmp_client import SnmpError
from homeassistant.data_entry_flow import FlowResultType
from tests.fakes import FakeSnmpClient
from tests.helpers import parse_var_table
from tests.test_discovery import FIXTURE

pytest_plugins = "pytest_homeassistant_custom_component"

_FAKE_DEVICE_INFO = DeviceInfo(
    device_index=1,
    name="PDU-MAN",
    alias="PDU",
    serial="12600347",
    firmware="V5.15.50_11",
    hardware="V2.00",
    chassis_oid=(1, 3, 6, 1, 4, 1, 2606, 7, 7, 4, 14848),
)


def _patch_successful_enquire(monkeypatch):
    unit_map = build_unit_map(parse_var_table(FIXTURE))

    async def fake_test_connection(client):
        return None

    async def fake_enquire(client, device_index=1):
        return _FAKE_DEVICE_INFO, unit_map

    monkeypatch.setattr(config_flow_module, "test_connection", fake_test_connection)
    monkeypatch.setattr(config_flow_module, "enquire", fake_enquire)

    # After the flow creates the entry, HA immediately calls
    # async_setup_entry (__init__.py), which builds its own SnmpClient and
    # polls it via the coordinator -- patch that too so entry setup doesn't
    # try to hit a real socket in this test.
    monkeypatch.setattr(integration_module, "build_client", lambda data: FakeSnmpClient())
    return unit_map


async def test_v2c_happy_path_creates_entry(hass, enable_custom_integrations, monkeypatch):
    unit_map = _patch_successful_enquire(monkeypatch)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.216", "port": 161, "snmp_version": "2c"},
    )
    assert result["step_id"] == "v1v2_credentials"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"read_community": "public", "write_community": "pdu"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"]["name"] == "PDU-MAN"
    assert result["description_placeholders"]["outlet_count"] == str(len(unit_map.outlets))

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rittal PDU (192.168.1.216)"
    assert result["data"]["read_community"] == "public"
    assert result["data"]["write_community"] == "pdu"
    assert "unit_map" in result["data"]


async def test_v3_selection_routes_to_v3_credentials_step(hass, enable_custom_integrations, monkeypatch):
    _patch_successful_enquire(monkeypatch)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.216", "port": 161, "snmp_version": "3"},
    )
    assert result["step_id"] == "v3_credentials"


async def test_connection_failure_shows_cannot_connect_error(hass, enable_custom_integrations, monkeypatch):
    async def failing_test_connection(client):
        raise SnmpError("simulated timeout")

    monkeypatch.setattr(config_flow_module, "test_connection", failing_test_connection)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"host": "192.168.1.216", "port": 161, "snmp_version": "2c"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"read_community": "public", "write_community": ""},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "v1v2_credentials"
    assert result["errors"] == {"base": "cannot_connect"}
