"""Data update coordinator for the KOSPEL PPE4 integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Ppe4Client, Ppe4Error
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    INVALID_VALUE,
    LIVE_BLOCKS,
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    WRITE_GROUP_COUNT,
    WRITE_GROUP_START,
)
from .registers import (
    OPTION_SCAN_INTERVAL,
    FaultConfig,
    FaultState,
    ResolvedRegister,
    build_write_group,
    decode_faults,
    resolve_fault_config,
    resolve_register_map,
    scale_value,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Ppe4Data:
    """Data returned by one poll of the heater."""

    registers: dict[int, float | int]
    fault: FaultState | None

    def raw(self, register: int) -> float | int | None:
        """Return the raw value of one register."""
        return self.registers.get(register)


class Ppe4Coordinator(DataUpdateCoordinator[Ppe4Data]):
    """Poll the heater and expose scaled values."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: Ppe4Client,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self._options: dict[str, Any] = dict(entry.options)
        self.register_map: dict[str, ResolvedRegister] = resolve_register_map(
            self._options
        )
        self.fault_config: FaultConfig | None = resolve_fault_config(self._options)
        scan_interval = self._options.get(OPTION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        try:
            interval = int(scan_interval)
        except (TypeError, ValueError):
            interval = DEFAULT_SCAN_INTERVAL
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> Ppe4Data:
        """Fetch the live register blocks."""
        try:
            registers = await self.client.async_read_blocks(LIVE_BLOCKS)
        except Ppe4Error as err:
            raise UpdateFailed(str(err)) from err

        fault: FaultState | None = None
        if self.fault_config is not None:
            value = registers.get(self.fault_config.register)
            fault = decode_faults(value, self.fault_config.encoding)

        return Ppe4Data(registers=registers, fault=fault)

    def scaled(self, key: str) -> float | None:
        """Return one logical value with its scale applied."""
        if self.data is None:
            return None
        resolved = self.register_map.get(key)
        if resolved is None:
            return None
        raw = self.data.registers.get(resolved.register)
        if raw is None or raw == INVALID_VALUE:
            return None
        return scale_value(raw, resolved.scale)

    def raw_value(self, key: str) -> float | int | None:
        """Return one logical value without scaling."""
        if self.data is None:
            return None
        resolved = self.register_map.get(key)
        if resolved is None:
            return None
        return self.data.registers.get(resolved.register)

    @property
    def target_register(self) -> int:
        """Return the register used for the target temperature."""
        return self.register_map["target_temperature"].register

    @property
    def target_scale(self) -> float:
        """Return the scale used for the target temperature."""
        return self.register_map["target_temperature"].scale

    async def async_set_target_temperature(self, temperature: float) -> None:
        """Write a new target temperature.

        The vendor app always writes the whole five-register settings group,
        so the current group is read first and written back with only the
        target register replaced.  This avoids clobbering unknown fields.
        """
        if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
            raise ValueError(f"Temperature {temperature} °C is outside the allowed range")

        target = self.target_register
        scale = self.target_scale or 1.0
        raw_target = int(round(temperature / scale))

        group = tuple(
            range(WRITE_GROUP_START, WRITE_GROUP_START + WRITE_GROUP_COUNT)
        )
        if target in group:
            try:
                current = await self.client.async_read_block(
                    WRITE_GROUP_START, WRITE_GROUP_COUNT
                )
            except Ppe4Error as err:
                raise Ppe4Error(
                    "Cannot read the settings group before writing the setpoint"
                ) from err
            values = build_write_group(current, group, target, raw_target)
        else:
            values = {target: raw_target}
        try:
            await self.client.async_write_registers(values)
        except Ppe4Error as err:
            raise Ppe4Error(str(err)) from err

        await self.async_request_refresh()
