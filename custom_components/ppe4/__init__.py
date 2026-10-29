"""The KOSPEL PPE4 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Ppe4Client, Ppe4Error
from .const import DEFAULT_PORT, DEFAULT_TIMEOUT, DOMAIN
from .coordinator import Ppe4Coordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]

type Ppe4ConfigEntry = ConfigEntry[Ppe4Coordinator]

SERVICE_READ_REGISTERS = "read_registers"
SERVICE_WRITE_REGISTERS = "write_registers"

READ_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Required("start"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Required("count"): vol.All(vol.Coerce(int), vol.Range(min=1, max=256)),
    }
)

WRITE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Required("registers"): dict,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration-wide actions."""
    hass.data.setdefault(DOMAIN, {})

    if not hass.services.has_service(DOMAIN, SERVICE_READ_REGISTERS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_READ_REGISTERS,
            _async_read_registers,
            schema=READ_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_WRITE_REGISTERS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_WRITE_REGISTERS,
            _async_write_registers,
            schema=WRITE_SCHEMA,
        )
    return True


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> Ppe4Coordinator:
    """Resolve the coordinator targeted by a service call."""
    entries: dict[str, Ppe4Coordinator] = hass.data.get(DOMAIN, {})
    entry_id = call.data.get("entry_id")
    if entry_id:
        coordinator = entries.get(entry_id)
        if coordinator is None:
            raise HomeAssistantError(f"Unknown PPE4 config entry: {entry_id}")
        return coordinator
    if len(entries) == 1:
        return next(iter(entries.values()))
    if not entries:
        raise HomeAssistantError("No PPE4 heater is configured")
    raise HomeAssistantError(
        "Several PPE4 heaters are configured; pass entry_id to select one"
    )


async def _async_read_registers(call: ServiceCall) -> dict[str, Any]:
    """Read an arbitrary register block from the heater."""
    coordinator = _get_coordinator(call.hass, call)
    start = call.data["start"]
    count = call.data["count"]
    try:
        registers = await coordinator.client.async_read_block(start, count)
    except Ppe4Error as err:
        raise HomeAssistantError(str(err)) from err
    return {"registers": {str(key): value for key, value in registers.items()}}


async def _async_write_registers(call: ServiceCall) -> None:
    """Write a mapping of register numbers to integer values."""
    coordinator = _get_coordinator(call.hass, call)
    values: dict[int, int] = {}
    for raw_register, raw_value in call.data["registers"].items():
        try:
            values[int(raw_register)] = int(raw_value)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(
                "Invalid register/value pair: "
                f"{raw_register!r}={raw_value!r} (integers expected)"
            ) from err
    if not values:
        raise HomeAssistantError("No registers to write")
    try:
        await coordinator.client.async_write_registers(values)
    except Ppe4Error as err:
        raise HomeAssistantError(str(err)) from err
    await coordinator.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: Ppe4ConfigEntry) -> bool:
    """Set up KOSPEL PPE4 from a config entry."""
    session = async_get_clientsession(hass)
    client = Ppe4Client(
        session,
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        timeout=DEFAULT_TIMEOUT,
    )
    coordinator = Ppe4Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: Ppe4ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: Ppe4ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
