"""Binary sensor platform for the KOSPEL PPE4 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Ppe4Coordinator
from .entity import Ppe4Entity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry


class Ppe4ProblemSensor(Ppe4Entity, BinarySensorEntity):
    """On when the heater reports any fault."""

    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: Ppe4Coordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry, "problem")

    @property
    def is_on(self) -> bool | None:
        """Return true when an error is active."""
        if self.coordinator.data is None:
            return None
        error = self.coordinator.data.error
        return bool(error and error.active)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Expose the decoded error codes."""
        if self.coordinator.data is None or self.coordinator.data.error is None:
            return None
        error = self.coordinator.data.error
        return {
            "codes": list(error.codes),
            "unknown_values": list(error.unknown),
            "registers": {str(k): v for k, v in error.values.items()},
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator: Ppe4Coordinator = entry.runtime_data
    async_add_entities([Ppe4ProblemSensor(coordinator, entry)])
