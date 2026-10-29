"""Water heater platform for the KOSPEL PPE4 integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.water_heater import (
    STATE_OFF,
    STATE_ON,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    TARGET_TEMPERATURE_STEP,
)
from .coordinator import Ppe4Coordinator
from .entity import Ppe4Entity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class Ppe4WaterHeater(Ppe4Entity, WaterHeaterEntity):
    """The PPE4.M instantaneous water heater."""

    _attr_translation_key = "water_heater"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = MIN_TEMPERATURE
    _attr_max_temp = MAX_TEMPERATURE
    _attr_target_temperature_step = TARGET_TEMPERATURE_STEP
    _attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE

    def __init__(self, coordinator: Ppe4Coordinator, entry: ConfigEntry) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, entry, "water_heater")

    @property
    def current_temperature(self) -> float | None:
        """Return the outlet water temperature."""
        return self.coordinator.scaled("current_temperature")

    @property
    def target_temperature(self) -> float | None:
        """Return the configured setpoint."""
        return self.coordinator.scaled("target_temperature")

    @property
    def current_operation(self) -> str:
        """Return on while the heater is drawing power."""
        power = self.coordinator.scaled("power")
        return STATE_ON if power and power > 0 else STATE_OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw registers used by the entity."""
        return {
            "current_temperature_register": self.coordinator.register_map[
                "current_temperature"
            ].register,
            "target_temperature_register": self.coordinator.target_register,
            "power_kw": self.coordinator.scaled("power"),
            "flow_l_min": self.coordinator.scaled("flow_rate"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        try:
            await self.coordinator.async_set_target_temperature(float(temperature))
        except (ValueError, HomeAssistantError) as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:  # noqa: BLE001 - surfaced to the user
            _LOGGER.exception("Failed to set target temperature")
            raise HomeAssistantError(f"Cannot set target temperature: {err}") from err


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the water heater entity."""
    coordinator: Ppe4Coordinator = entry.runtime_data
    async_add_entities([Ppe4WaterHeater(coordinator, entry)])
