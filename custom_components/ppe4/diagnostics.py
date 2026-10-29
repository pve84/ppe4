"""Diagnostics support for the KOSPEL PPE4 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST

from .const import FAULTS

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    registers: dict[str, Any] = {}
    if data is not None:
        registers = {str(key): value for key, value in sorted(data.registers.items())}

    errors: dict[str, Any] | None = None
    if data is not None and data.error is not None:
        errors = {
            "codes": list(data.error.codes),
            "texts": [FAULTS.get(code) for code in data.error.codes],
            "unknown_values": list(data.error.unknown),
            "registers": {str(k): v for k, v in data.error.values.items()},
        }

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "register_map": {
            key: {"register": resolved.register, "scale": resolved.scale}
            for key, resolved in coordinator.register_map.items()
        },
        "error_config": (
            None
            if coordinator.error_config is None
            else {
                "registers": list(coordinator.error_config.registers),
                "encoding": coordinator.error_config.encoding,
            }
        ),
        "registers": registers,
        "errors": errors,
    }
