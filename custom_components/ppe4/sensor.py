"""Sensor platform for the KOSPEL PPE4 integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FAULTS, FAULTS_PL, FAULT_SPEC
from .coordinator import Ppe4Coordinator
from .entity import Ppe4Entity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class Ppe4SensorDescription(SensorEntityDescription):
    """Description of a register-backed sensor."""

    register_key: str = ""


def _as_device_class(value: str | None) -> SensorDeviceClass | None:
    """Return a SensorDeviceClass for a constant name, if valid."""
    if not value:
        return None
    try:
        return SensorDeviceClass(value)
    except ValueError:
        _LOGGER.debug("Unsupported device class: %s", value)
        return None


def _as_entity_category(value: str | None) -> EntityCategory | None:
    """Return an EntityCategory for a constant name, if valid."""
    if not value:
        return None
    try:
        return EntityCategory(value)
    except ValueError:
        _LOGGER.debug("Unsupported entity category: %s", value)
        return None


def _as_state_class(value: str | None) -> SensorStateClass | None:
    """Return a SensorStateClass for a constant name, if valid."""
    if not value:
        return None
    try:
        return SensorStateClass(value)
    except ValueError:
        _LOGGER.debug("Unsupported state class: %s", value)
        return None


class Ppe4RegisterSensor(Ppe4Entity, SensorEntity):
    """A sensor backed by one heater register."""

    entity_description: Ppe4SensorDescription

    def __init__(
        self,
        coordinator: Ppe4Coordinator,
        entry: ConfigEntry,
        description: Ppe4SensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, description.unique_id or description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_suggested_display_precision = description.suggested_display_precision
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> float | None:
        """Return the scaled register value."""
        return self.coordinator.scaled(self.entity_description.register_key)


class Ppe4FaultCodeSensor(Ppe4Entity, SensorEntity):
    """Raw fault register value."""

    _attr_translation_key = FAULT_SPEC.translation_key
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Ppe4Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, FAULT_SPEC.key)

    @property
    def native_value(self) -> int | None:
        """Return the raw fault word."""
        if self.coordinator.data is None or self.coordinator.data.fault is None:
            return None
        return self.coordinator.data.fault.raw

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the encoding and the configured register."""
        config = self.coordinator.fault_config
        if config is None:
            return None
        return {"register": config.register, "encoding": config.encoding}


class Ppe4ActiveFaultsSensor(Ppe4Entity, SensorEntity):
    """Number of active faults, with the decoded texts as attributes."""

    _attr_translation_key = "active_faults"
    _attr_icon = "mdi:alert-outline"
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator: Ppe4Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "active_faults")

    @property
    def native_value(self) -> int | None:
        """Return the number of active faults."""
        if self.coordinator.data is None or self.coordinator.data.fault is None:
            return None
        return len(self.coordinator.data.fault.codes)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the decoded fault list."""
        if self.coordinator.data is None or self.coordinator.data.fault is None:
            return None
        fault = self.coordinator.data.fault
        return {
            "faults": [
                {"code": code, "text": FAULTS.get(code, f"Unknown fault {code}")}
                for code in fault.codes
            ],
            "faults_pl": [
                {"code": code, "text": FAULTS_PL.get(code, "")} for code in fault.codes
            ],
            "raw": fault.raw,
            "unknown_bits": fault.unknown_bits,
        }


def _build_descriptions(coordinator: Ppe4Coordinator) -> list[Ppe4SensorDescription]:
    """Build one sensor description per resolved register."""
    descriptions: list[Ppe4SensorDescription] = []
    for key, resolved in coordinator.register_map.items():
        spec = resolved.spec
        descriptions.append(
            Ppe4SensorDescription(
                key=key,
                register_key=key,
                translation_key=spec.translation_key,
                native_unit_of_measurement=spec.unit,
                device_class=_as_device_class(spec.device_class),
                state_class=_as_state_class(spec.state_class),
                suggested_display_precision=spec.precision,
                icon=spec.icon,
                entity_category=_as_entity_category(spec.entity_category),
            )
        )
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator: Ppe4Coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        Ppe4RegisterSensor(coordinator, entry, description)
        for description in _build_descriptions(coordinator)
    ]
    if coordinator.fault_config is not None:
        entities.append(Ppe4FaultCodeSensor(coordinator, entry))
        entities.append(Ppe4ActiveFaultsSensor(coordinator, entry))
    async_add_entities(entities)
