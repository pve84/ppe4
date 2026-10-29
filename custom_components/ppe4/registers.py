"""Register map resolution and fault decoding helpers.

Kept free of Home Assistant imports so the logic is unit-testable on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .const import (
    DEFAULT_ERROR_REGISTERS,
    ERROR_ENCODING_BITMASK,
    ERROR_ENCODING_CODE,
    ERROR_ENCODINGS,
    FAULT_COUNT,
    REGISTER_SPECS,
    RegisterSpec,
)

#: Option key holding the per-value register overrides.
OPTION_REGISTERS: Final = "registers"
#: Option key holding the registers that carry error codes.
OPTION_ERROR_REGISTERS: Final = "error_registers"
#: Option key selecting how the error registers are decoded.
OPTION_ERROR_ENCODING: Final = "error_encoding"
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
class ErrorConfig:
    """Registers that carry error codes."""

    registers: tuple[int, ...]
    encoding: str


@dataclass(frozen=True, kw_only=True)
class ErrorState:
    """Decoded error state for one poll."""

    codes: tuple[int, ...]
    values: dict[int, int]
    unknown: tuple[int, ...] = ()

    @property
    def active(self) -> bool:
        """Return True when at least one error is present."""
        return bool(self.codes or self.unknown)


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


def _parse_register_list(value: Any) -> tuple[int, ...]:
    """Parse a comma separated string or list of register numbers."""
    if value is None:
        return DEFAULT_ERROR_REGISTERS
    if isinstance(value, str):
        items: list[Any] = [item for item in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return DEFAULT_ERROR_REGISTERS
    registers: list[int] = []
    for item in items:
        if isinstance(item, str):
            item = item.strip()
            if not item:
                continue
        try:
            register = int(item)
        except (TypeError, ValueError):
            continue
        if register > 0:
            registers.append(register)
    return tuple(registers)


def resolve_error_config(
    options: Mapping[str, Any] | None = None,
) -> ErrorConfig | None:
    """Return the error register configuration.

    Error handling is always on unless it is explicitly disabled; the default
    registers are the four code slots recovered from the vendor app.
    """
    options = options or {}
    encoding = str(options.get(OPTION_ERROR_ENCODING, ERROR_ENCODING_CODE))
    if encoding not in ERROR_ENCODINGS:
        encoding = ERROR_ENCODING_CODE
    registers = _parse_register_list(options.get(OPTION_ERROR_REGISTERS))
    if not registers:
        return None
    return ErrorConfig(registers=registers, encoding=encoding)


def decode_errors(
    registers: Mapping[int, float | int], config: ErrorConfig
) -> ErrorState:
    """Decode the configured error registers.

    ``code`` treats each register as one catalogue code (1..29).
    ``bitmask`` treats each register as a bitfield where bit ``n`` is code
    ``n + 1`` (up to 16 codes per register).
    """
    codes: list[int] = []
    values: dict[int, int] = {}
    unknown: list[int] = []

    for register in config.registers:
        raw_value = registers.get(register)
        if raw_value is None:
            continue
        raw = int(raw_value)
        values[register] = raw
        if raw in (0, 65535):
            continue
        if config.encoding == ERROR_ENCODING_BITMASK:
            for bit in range(16):
                if raw & (1 << bit):
                    code = bit + 1
                    if code <= FAULT_COUNT and code not in codes:
                        codes.append(code)
        elif 1 <= raw <= FAULT_COUNT:
            if raw not in codes:
                codes.append(raw)
        else:
            unknown.append(raw)

    return ErrorState(codes=tuple(codes), values=values, unknown=tuple(unknown))


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
