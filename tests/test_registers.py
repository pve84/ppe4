"""Tests for register-map resolution and fault decoding."""

from __future__ import annotations

from custom_components.ppe4.const import (
    ERROR_ENCODING_BITMASK,
    ERROR_ENCODING_CODE,
)
from custom_components.ppe4.registers import (
    build_write_group,
    decode_errors,
    resolve_error_config,
    resolve_register_map,
    scale_value,
)


def test_default_register_map() -> None:
    """The shipped map resolves to the recovered registers."""
    register_map = resolve_register_map()
    assert register_map["current_temperature"].register == 1135
    assert register_map["target_temperature"].register == 1391
    assert register_map["target_temperature"].scale == 0.1
    assert register_map["flow_rate"].register == 1137
    assert register_map["power"].register == 1138
    assert register_map["inlet_temperature"].register == 1134
    assert register_map["max_temperature"].register == 1388


def test_register_override_integer() -> None:
    """A plain integer override replaces the register, keeping the scale."""
    register_map = resolve_register_map({"registers": {"current_temperature": 1200}})
    assert register_map["current_temperature"].register == 1200
    assert register_map["current_temperature"].scale == 0.1


def test_register_override_with_scale() -> None:
    """A two-element override also replaces the scale."""
    register_map = resolve_register_map(
        {"registers": {"target_temperature": [1391, 1.0]}}
    )
    assert register_map["target_temperature"].register == 1391
    assert register_map["target_temperature"].scale == 1.0


def test_invalid_override_is_ignored() -> None:
    """Bad override shapes fall back to the defaults."""
    register_map = resolve_register_map(
        {"registers": {"current_temperature": "nope", "unknown": 1}}
    )
    assert register_map["current_temperature"].register == 1135


def test_error_config_defaults() -> None:
    """Errors are decoded from the four default slots."""
    config = resolve_error_config({})
    assert config is not None
    assert config.registers == (1253,)
    assert config.encoding == ERROR_ENCODING_CODE


def test_error_config_from_string() -> None:
    """A comma separated option overrides the slots."""
    config = resolve_error_config({"error_registers": "1200, 1201"})
    assert config is not None
    assert config.registers == (1200, 1201)


def test_error_config_disabled_without_registers() -> None:
    """No valid registers disables error decoding."""
    assert resolve_error_config({"error_registers": ""}) is None
    assert resolve_error_config({"error_registers": "abc"}) is None


def test_decode_code_slots() -> None:
    """Each register holds one catalogue code."""
    config = resolve_error_config({})
    state = decode_errors({1253: 4}, config)
    assert state.codes == (4,)
    assert state.active is True
    assert state.values == {1253: 4}


def test_decode_no_errors() -> None:
    """All-zero slots mean OK."""
    config = resolve_error_config({})
    state = decode_errors({1253: 0}, config)
    assert state.active is False
    assert state.codes == ()


def test_decode_code_out_of_catalogue() -> None:
    """A value outside 1..29 is reported as unknown, not silently dropped."""
    config = resolve_error_config({})
    state = decode_errors({1253: 99}, config)
    assert state.codes == ()
    assert state.unknown == (99,)
    assert state.active is True


def test_decode_bitmask() -> None:
    """Bit n maps to catalogue code n+1."""
    config = resolve_error_config({"error_encoding": "bitmask"})
    assert config is not None
    state = decode_errors({1253: 0b1010}, config)
    assert state.codes == (2, 4)


def test_decode_ignores_invalid_sentinel() -> None:
    """65535 means 'no reading' and is not an error."""
    config = resolve_error_config({})
    state = decode_errors({1253: 65535}, config)
    assert state.codes == ()
    assert state.unknown == ()
    assert state.active is False


def test_build_write_group_preserves_members() -> None:
    """Only the target register changes in the group write."""
    current = {1390: 0, 1391: 500, 1392: 450, 1393: 500, 1394: 550}
    values = build_write_group(current, tuple(range(1390, 1395)), 1391, 470)
    assert values == {1390: 0, 1391: 470, 1392: 450, 1393: 500, 1394: 550}


def test_build_write_group_single_register() -> None:
    """A target outside the group is written alone."""
    values = build_write_group({1390: 0}, (1390, 1391), 1200, 470)
    assert values == {1200: 470}


def test_scale_value() -> None:
    """Scaling multiplies by the configured factor."""
    assert scale_value(452, 0.1) == 45.2
    assert scale_value(None, 0.1) is None
