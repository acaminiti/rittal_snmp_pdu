"""Tests for SnmpClient's non-network logic: credential selection, GET
chunking, and SET value typing. Network calls (get_cmd/set_cmd/etc.) are
monkeypatched -- these tests never touch a socket.
"""
from custom_components.rittal_snmp_pdu import snmp_client as snmp_client_module
from custom_components.rittal_snmp_pdu.snmp_client import (
    Integer32,
    SnmpClient,
    SnmpV1V2Credentials,
    SnmpV3Credentials,
    SnmpVersion,
)


def _make_client(version=SnmpVersion.V2C, **credential_kwargs):
    credentials = SnmpV1V2Credentials(**credential_kwargs) if credential_kwargs else None
    return SnmpClient(host="192.0.2.1", port=161, version=version, credentials=credentials)


def test_auth_data_uses_read_community_by_default():
    client = _make_client(read_community="public", write_community="pdu")
    auth = client._auth_data()
    assert auth.communityName == "public"


def test_auth_data_uses_write_community_when_writing():
    client = _make_client(read_community="public", write_community="pdu")
    auth = client._auth_data(write=True)
    assert auth.communityName == "pdu"


def test_auth_data_write_falls_back_to_read_community_when_unset():
    client = _make_client(read_community="public")
    auth = client._auth_data(write=True)
    assert auth.communityName == "public"


def test_auth_data_v1_uses_mp_model_0():
    client = _make_client(version=SnmpVersion.V1, read_community="public")
    auth = client._auth_data()
    assert auth.message_processing_model == 0


def test_auth_data_v2c_uses_mp_model_1():
    client = _make_client(version=SnmpVersion.V2C, read_community="public")
    auth = client._auth_data()
    assert auth.message_processing_model == 1


def test_auth_data_v3_uses_usm_credentials():
    client = SnmpClient(
        host="192.0.2.1",
        port=161,
        version=SnmpVersion.V3,
        credentials=SnmpV3Credentials(username="admin"),
    )
    auth = client._auth_data()
    assert auth.userName == "admin"


async def test_get_bulk_many_chunks_and_merges_results(monkeypatch):
    client = _make_client(read_community="public")
    calls: list[list[tuple]] = []

    async def fake_get_many(oids):
        calls.append(list(oids))
        return {oid: oid[-1] for oid in oids}  # value = last OID component

    monkeypatch.setattr(client, "get_many", fake_get_many)
    monkeypatch.setattr(client, "_GET_CHUNK_SIZE", 3)

    oids = [(1, i) for i in range(10)]
    result = await client.get_bulk_many(oids)

    assert len(calls) == 4  # 10 oids / chunk size 3 -> 4 chunks (3,3,3,1)
    assert [len(c) for c in calls] == [3, 3, 3, 1]
    assert result == {oid: oid[-1] for oid in oids}


async def test_set_wraps_plain_int_in_integer32(monkeypatch):
    """Regression test for the "'int' object has no attribute 'getTagSet'"
    failure: SET must wrap the raw Python int in an ASN.1 Integer32 before
    handing it to pysnmp, not pass it through as-is."""
    client = _make_client(read_community="public", write_community="pdu")

    real_integer32 = Integer32
    calls: list[int] = []

    def spying_integer32(value):
        calls.append(value)
        return real_integer32(value)

    monkeypatch.setattr(snmp_client_module, "Integer32", spying_integer32)

    async def fake_set_cmd(engine, auth, transport, context, var_bind, **options):
        return None, 0, 0, [var_bind]

    monkeypatch.setattr(snmp_client_module, "set_cmd", fake_set_cmd)

    async def fake_transport():
        return object()

    monkeypatch.setattr(client, "_transport", fake_transport)

    await client.set((1, 3, 6, 1), 1)

    assert calls == [1]
