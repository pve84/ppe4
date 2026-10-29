"""Register map resolution and fault decoding helpers.

Kept free of Home Assistant imports so the logic is unit-testable on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .const import (
    FAULT_COUNT,
    FAULT_ENCODING_CODE,
    FAULT_ENCODING_NONE,
    FAULT_ENCODINGS,
    FAULT_SPEC,
    REGISTER_SPECS,
    RegisterSpec,
)

#: Option key holding the per-value register overrides.
OPTION_REGISTERS: Final = "registers"
#: Option key holding the optional fault register.
OPTION_FAULT_REGISTER: Final = "fault_register"
#: Option key selecting how the fault register is decoded.
OPTION_FAULT_ENCODING: Final = "fault_encoding"
#: Option key for the polling interval.
OPTION_SCAN_INTERVAL: Final = "scan_interval"


@dataclass(frozen=True, kw_only=True)
class ResolvedRegister:
    """One logical value resolved to a concrete register and scale."""

    key: str
    register: int
    scale: float
    spec: RegisterSpec


@dataclass(frozen=True, kw_only=True)
class FaultConfig:
    """Fault register configuration."""

    register: int
    encoding: str


@dataclass(frozen=True, kw_only=True)
class FaultState:
    """Decoded fault state for one poll."""

    raw: int
    codes: tuple[int, ...]
    unknown_bits: int = 0


def _parse_override(value: Any) -> tuple[int, float | None] | None:
    """Parse one option override, either ``reg`` or ``[reg, scale]``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value, None
    if isinstance(value, (list, tuple)) and 1 <= len(value) <= 2:
        try:
            register = int(value[0])
        except (TypeError, ValueError):
            return None
        scale: float | None = None
        if len(value) == 2:
            try:
                scale = float(value[1])
            except (TypeError, ValueError):
                return None
        return register, scale
    return None


def resolve_register_map(
    options: Mapping[str, Any] | None = None,
) -> dict[str, ResolvedRegister]:
    """Return the effective register map for the given options."""
    options = options or {}
    overrides = options.get(OPTION_REGISTERS) or {}
    if not isinstance(overrides, Mapping):
        overrides = {}

    resolved: dict[str, ResolvedRegister] = {}
    for spec in REGISTER_SPECS:
        register = spec.register
        scale = spec.scale
        override = _parse_override(overrides.get(spec.key))
        if override is not None:
            register, override_scale = override
            if override_scale is not None:
                scale = override_scale
        resolved[spec.key] = ResolvedRegister(
            key=spec.key, register=register, scale=scale, spec=spec
        )
    return resolved


def resolve_fault_config(
    options: Mapping[str, Any] | None = None,
) -> FaultConfig | None:
    """Return the fault register configuration, if enabled."""
    options = options or {}
    encoding = options.get(OPTION_FAULT_ENCODING, FAULT_ENCODING_NONE)
    if encoding not in FAULT_ENCODINGS or encoding == FAULT_ENCODING_NONE:
        return None
    raw_register = options.get(OPTION_FAULT_REGISTER)
    if raw_register in (None, "", "none"):
        return None
    try:
        register = int(raw_register)
    except (TypeError, ValueError):
        return None
    if register <= 0:
        return None
    return FaultConfig(register=register, encoding=str(encoding))


def fault_register_spec(config: FaultConfig) -> RegisterSpec:
    """Return the spec used for the raw fault register sensor."""
    return RegisterSpec(
        key=FAULT_SPEC.key,
        register=config.register,
        translation_key=FAULT_SPEC.translation_key,
        scale=FAULT_SPEC.scale,
        unit=None,
        device_class=None,
        state_class=None,
        icon=FAULT_SPEC.icon,
    )


def decode_faults(value: float | int | None, encoding: str) -> FaultState:
    """Decode the fault register value into catalogue codes.

    ``bitmask`` uses bit ``n`` for catalogue code ``n + 1`` (29 bits).
    ``code`` treats the value itself as a catalogue code.
    """
    if value is None:
        return FaultState(raw=0, codes=())
    raw = int(value)
    if raw == 0:
        return FaultState(raw=0, codes=())

    if encoding == FAULT_ENCODING_CODE:
        if 1 <= raw <= FAULT_COUNT:
            return FaultState(raw=raw, codes=(raw,))
        return FaultState(raw=raw, codes=(), unknown_bits=raw)

    codes = tuple(bit + 1 for bit in range(FAULT_COUNT) if raw & (1 << bit))
    unknown = raw >> FAULT_COUNT
    return FaultState(raw=raw, codes=codes, unknown_bits=unknown)


def build_write_group(
    current: Mapping[int, float | int],
    registers: "tuple[int, ...]",
    target: int,
    raw_value: int,
) -> dict[int, int]:
    """Return the group write payload with one register replaced.

    The vendor app writes the whole settings group at once; preserving the
    other members keeps unknown fields untouched.
    """
    if target not in registers:
        return {target: raw_value}
    values = {
        register: int(current[register])
        for register in registers
        if register in current
    }
    values[target] = raw_value
    return values


def scale_value(raw: float | int | None, scale: float) -> float | None:
    """Apply a register scale factor."""
    if raw is None:
        return None
    return float(raw) * scale
