"""Constants and OID layout for the Rittal CMC III SNMP agent.

Mirrors /home/acaminiti/.snmp/mibs/RITTAL-CMC-III-MIB (cmcIII subtree,
enterprises.2606.7). Only the pieces actually used by discovery/polling
are reproduced here; see the MIB for the full picture.
"""
from __future__ import annotations

from enum import IntEnum

DOMAIN = "rittal_snmp_pdu"

DEFAULT_PORT = 161
DEFAULT_SCAN_INTERVAL = 30
CONF_SCAN_INTERVAL = "scan_interval"

# --- cmcIII OID roots ---------------------------------------------------
CMC3_BASE = (1, 3, 6, 1, 4, 1, 2606, 7)

UNIT_STATUS_OID = CMC3_BASE + (2, 1, 0)  # cmcIIIUnitStatus
UNIT_SERIAL_OID = CMC3_BASE + (2, 6, 0)  # cmcIIIUnitSerial
UNIT_FW_REV_OID = CMC3_BASE + (2, 4, 0)  # cmcIIIUnitFWRev

# cmcIIIDevTable ::= { cmcIIIDevice(4) cmcIIIDevs(1) cmcIIIDevTable(2) }
DEV_TABLE_BASE = CMC3_BASE + (4, 1, 2, 1)
DEV_NAME_COL = 2  # cmcIIIDevName
DEV_ALIAS_COL = 3  # cmcIIIDevAlias
DEV_TYPE_COL = 4  # cmcIIIDevType (OID into cmcIIIProductChassis)
DEV_SERIAL_COL = 13  # cmcIIIDevSerial
DEV_FW_COL = 11  # cmcIIIDevFW
DEV_HW_COL = 12  # cmcIIIDevHW
DEV_NUMBER_OF_VARS_COL = 17  # cmcIIIDevNumberOfVars

# cmcIIIVarTable ::= { cmcIIIDevice(4) cmcIIIVars(2) cmcIIIVarTable(2) }
VAR_TABLE_BASE = CMC3_BASE + (4, 2, 2, 1)
VAR_NAME_COL = 3  # cmcIIIVarName
VAR_TYPE_COL = 4  # cmcIIIVarType
VAR_UNIT_COL = 5  # cmcIIIVarUnit
VAR_DATA_TYPE_COL = 6  # cmcIIIVarDataType
VAR_SCALE_COL = 7  # cmcIIIVarScale
VAR_VALUE_STR_COL = 10  # cmcIIIVarValueStr
VAR_VALUE_INT_COL = 11  # cmcIIIVarValueInt
VAR_ACCESS_COL = 13  # cmcIIIVarAccess
VAR_QUALITY_COL = 14  # cmcIIIVarQuality

# cmcIIIProductChassis ::= { cmcIIIProducts(7) cmcIIIProductChassis(4) }
PRODUCT_CHASSIS_BASE = CMC3_BASE + (7, 4)


class VarType(IntEnum):
    """Subset of cmcIIIVarType actually used for classification."""

    VALUE = 2
    STATUS = 7
    OUTPUT = 20


class VarDataType(IntEnum):
    """cmcIIIVarDataType: what kind of value cmcIIIVarValueInt/Str hold."""

    NOT_AVAIL = 1
    INT = 2
    STRING = 3
    ENUM = 4


class VarAccess(IntEnum):
    """cmcIIIVarAccess: whether a var's value can be written, and how."""

    NONE = 1
    READONLY = 2
    READWRITE = 3
    READWRITE_SWITCH = 4
    READWRITE_EXTENDED = 5


class VarQuality(IntEnum):
    """cmcIIIVarQuality: the agent's own confidence/alarm state for a var.

    Drives entity availability/problem state; the "*_NO_VALUE" variants
    mean the same quality but with no value currently backing it.
    """

    UNDEFINED = 1
    OK = 2
    WARNING = 3
    ALARM = 4
    INFO = 5
    UNDEFINED_NO_VALUE = 21
    OK_NO_VALUE = 22
    WARNING_NO_VALUE = 23
    ALARM_NO_VALUE = 24
    INFO_NO_VALUE = 25


WRITABLE_ACCESS = {VarAccess.READWRITE, VarAccess.READWRITE_SWITCH, VarAccess.READWRITE_EXTENDED}

# Name-parsing structure -------------------------------------------------
SOCKETS_GROUP = "Sockets"
SOCKET_RELAY_LEAF = "General.Relay"
SOCKET_STATUS_LEAF = "General.Status"
ENERGY_CUSTOM_MARKER = "Custom"
