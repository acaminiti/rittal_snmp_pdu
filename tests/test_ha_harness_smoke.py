"""Smoke test: confirms pytest-homeassistant-custom-component's `hass`
fixture (and custom-integration loading) works in this environment before
building real tests on top of it.
"""
from custom_components.rittal_snmp_pdu.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


async def test_hass_fixture_works(hass):
    assert hass.state.value in ("RUNNING", "running")


async def test_custom_integration_is_discoverable(hass, enable_custom_integrations):
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    assert integration.domain == DOMAIN
