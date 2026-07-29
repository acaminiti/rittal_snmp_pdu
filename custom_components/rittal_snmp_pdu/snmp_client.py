"""Thin asyncio wrapper over pysnmp, supporting SNMPv1/v2c/v3.

Only the handful of operations the integration needs: GET a scalar, walk a
table column, and SET a writable var. Callers work in plain OID tuples and
Python values; all pysnmp types are confined to this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_cmd,
    bulk_walk_cmd,
    get_cmd,
    set_cmd,
    walk_cmd,
)
from pysnmp.hlapi.v3arch.asyncio.auth import (
    usmAesCfb128Protocol,
    usmHMACSHAAuthProtocol,
    usmNoPrivProtocol,
)


class SnmpVersion(str, Enum):
    V1 = "1"
    V2C = "2c"
    V3 = "3"


@dataclass
class SnmpV1V2Credentials:
    read_community: str
    write_community: str | None = None  # falls back to read_community if unset


@dataclass
class SnmpV3Credentials:
    username: str
    auth_protocol: str = usmHMACSHAAuthProtocol
    auth_key: str | None = None
    priv_protocol: str = usmAesCfb128Protocol
    priv_key: str | None = None


Credentials = SnmpV1V2Credentials | SnmpV3Credentials

Oid = tuple[int, ...]


class SnmpError(Exception):
    """Raised for any transport/protocol-level SNMP failure."""


class SnmpClient:
    """One client per configured PDU (host/port/version/credentials)."""

    def __init__(
        self,
        host: str,
        port: int,
        version: SnmpVersion,
        credentials: Credentials,
        timeout: float = 3.0,
        retries: int = 2,
    ) -> None:
        self._host = host
        self._port = port
        self._version = version
        self._credentials = credentials
        self._timeout = timeout
        self._retries = retries
        self._engine = SnmpEngine()

    def _auth_data(self, *, write: bool = False):
        if self._version in (SnmpVersion.V1, SnmpVersion.V2C):
            if not isinstance(self._credentials, SnmpV1V2Credentials):
                raise SnmpError("v1/v2c requires a community string")
            mp_model = 0 if self._version is SnmpVersion.V1 else 1
            community = self._credentials.read_community
            if write and self._credentials.write_community:
                community = self._credentials.write_community
            return CommunityData(community, mpModel=mp_model)

        if not isinstance(self._credentials, SnmpV3Credentials):
            raise SnmpError("v3 requires SNMPv3 credentials")
        creds = self._credentials
        priv_protocol = usmNoPrivProtocol if creds.priv_key is None else creds.priv_protocol
        return UsmUserData(
            creds.username,
            authKey=creds.auth_key,
            privKey=creds.priv_key,
            authProtocol=creds.auth_protocol,
            privProtocol=priv_protocol,
        )

    def _transport(self):
        return UdpTransportTarget.create(
            (self._host, self._port), timeout=self._timeout, retries=self._retries
        )

    async def get(self, oid: Oid) -> object:
        transport = await self._transport()
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            self._engine,
            self._auth_data(),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        if error_indication:
            raise SnmpError(str(error_indication))
        if error_status:
            raise SnmpError(error_status.prettyPrint())
        _name, value = var_binds[0]
        return value

    async def get_many(self, oids: list[Oid]) -> dict[Oid, object]:
        transport = await self._transport()
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            self._engine,
            self._auth_data(),
            transport,
            ContextData(),
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
        )
        if error_indication:
            raise SnmpError(str(error_indication))
        if error_status:
            raise SnmpError(error_status.prettyPrint())
        return {tuple(int(p) for p in name): value for name, value in var_binds}

    async def get_bulk_many(self, oids: list[Oid]) -> dict[Oid, object]:
        """Like get_many, but uses GETBULK when the version supports it."""
        if self._version is SnmpVersion.V1 or len(oids) <= 1:
            return await self.get_many(oids)

        transport = await self._transport()
        error_indication, error_status, _error_index, var_binds = await bulk_cmd(
            self._engine,
            self._auth_data(),
            transport,
            ContextData(),
            0,
            0,
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
        )
        if error_indication:
            raise SnmpError(str(error_indication))
        if error_status:
            raise SnmpError(error_status.prettyPrint())
        return {tuple(int(p) for p in name): value for name, value in var_binds[: len(oids)]}

    async def walk_column(self, prefix: Oid) -> dict[Oid, object]:
        """Walk every OID under `prefix`, returning {full_oid: value}."""
        transport = await self._transport()
        results: dict[Oid, object] = {}

        walker = (
            walk_cmd(
                self._engine,
                self._auth_data(),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(prefix)),
            )
            if self._version is SnmpVersion.V1
            else bulk_walk_cmd(
                self._engine,
                self._auth_data(),
                transport,
                ContextData(),
                0,
                25,
                ObjectType(ObjectIdentity(prefix)),
            )
        )

        async for error_indication, error_status, _error_index, var_binds in walker:
            if error_indication:
                raise SnmpError(str(error_indication))
            if error_status:
                raise SnmpError(error_status.prettyPrint())
            for name, value in var_binds:
                oid = tuple(int(p) for p in name)
                if oid[: len(prefix)] != prefix:
                    return results
                results[oid] = value
        return results

    async def set(self, oid: Oid, value: object) -> None:
        transport = await self._transport()
        error_indication, error_status, _error_index, _var_binds = await set_cmd(
            self._engine,
            self._auth_data(write=True),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid), value),
        )
        if error_indication:
            raise SnmpError(str(error_indication))
        if error_status:
            raise SnmpError(error_status.prettyPrint())
