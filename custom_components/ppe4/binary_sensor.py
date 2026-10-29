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
        """Return true when a fault is active."""
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.data.fault and self.coordinator.data.fault.raw)

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        """Expose the decoded fault codes."""
        if self.coordinator.data is None or self.coordinator.data.fault is None:
            return None
        fault = self.coordinator.data.fault
        return {"codes": list(fault.codes), "raw": fault.raw}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator: Ppe4Coordinator = entry.runtime_data
    if coordinator.fault_config is None:
        return
    async_add_entities([Ppe4ProblemSensor(coordinator, entry)])
