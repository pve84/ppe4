"""Tests for register-map resolution and fault decoding."""

from __future__ import annotations

from custom_components.ppe4.const import FAULT_ENCODING_BITMASK, FAULT_ENCODING_CODE
from custom_components.ppe4.registers import (
    decode_faults,
    resolve_fault_config,
    resolve_register_map,
    scale_value,
)


def test_default_register_map() -> None:
    """The shipped map resolves to the recovered registers."""
    register_map = resolve_register_map()
    assert register_map["current_temperature"].register == 1388
    assert register_map["target_temperature"].register == 1390
    assert register_map["flow_rate"].register == 1137
    assert register_map["power"].register == 1138
    assert register_map["inlet_temperature"].register == 1134
    assert register_map["outlet_temperature"].register == 1135


def test_register_override_integer() -> None:
    """A plain integer override replaces the register, keeping the scale."""
    register_map = resolve_register_map({"registers": {"current_temperature": 1200}})
    assert register_map["current_temperature"].register == 1200
    assert register_map["current_temperature"].scale == 0.1


def test_register_override_with_scale() -> None:
    """A two-element override also replaces the scale."""
    register_map = resolve_register_map(
        {"registers": {"target_temperature": [1390, 1.0]}}
    )
    assert register_map["target_temperature"].register == 1390
    assert register_map["target_temperature"].scale == 1.0


def test_invalid_override_is_ignored() -> None:
    """Bad override shapes fall back to the defaults."""
    register_map = resolve_register_map(
        {"registers": {"current_temperature": "nope", "unknown": 1}}
    )
    assert register_map["current_temperature"].register == 1388


def test_fault_config_disabled_by_default() -> None:
    """Fault handling is off until a register is configured."""
    assert resolve_fault_config({}) is None
    assert resolve_fault_config({"fault_encoding": "bitmask"}) is None


def test_fault_config_enabled() -> None:
    """A register plus encoding enables fault handling."""
    config = resolve_fault_config({"fault_encoding": "bitmask", "fault_register": 1389})
    assert config is not None
    assert config.register == 1389
    assert config.encoding == FAULT_ENCODING_BITMASK


def test_decode_bitmask() -> None:
    """Bit n maps to catalogue code n+1."""
    state = decode_faults(0b101, FAULT_ENCODING_BITMASK)
    assert state.codes == (1, 3)
    assert state.raw == 5
    assert state.unknown_bits == 0


def test_decode_bitmask_highest_code() -> None:
    """Bit 28 is catalogue code 29."""
    state = decode_faults(1 << 28, FAULT_ENCODING_BITMASK)
    assert state.codes == (29,)


def test_decode_bitmask_unknown_bits() -> None:
    """Bits above the catalogue are reported separately."""
    state = decode_faults((1 << 0) | (1 << 29), FAULT_ENCODING_BITMASK)
    assert state.codes == (1,)
    assert state.unknown_bits == 1


def test_decode_code() -> None:
    """Single-code encoding returns the code itself."""
    assert decode_faults(7, FAULT_ENCODING_CODE).codes == (7,)
    state = decode_faults(99, FAULT_ENCODING_CODE)
    assert state.codes == ()
    assert state.unknown_bits == 99


def test_decode_zero_and_none() -> None:
    """Zero and missing values mean no faults."""
    assert decode_faults(0, FAULT_ENCODING_BITMASK).codes == ()
    assert decode_faults(None, FAULT_ENCODING_BITMASK).codes == ()


def test_scale_value() -> None:
    """Scaling multiplies by the configured factor."""
    assert scale_value(452, 0.1) == 45.2
    assert scale_value(None, 0.1) is None
