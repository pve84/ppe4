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

from .const import FAULTS, FAULTS_PL, PANEL_ERRORS
from .coordinator import Ppe4Coordinator
from .entity import Ppe4Entity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


def _error_text(code: int) -> str:
    """Return the best description for one error code.

    The heater's own display uses the E01-E11 codes from the installation
    manual; codes without a panel meaning fall back to the diagnostic
    catalogue shipped in the vendor app.
    """
    if code in PANEL_ERRORS:
        return f"{code} ({PANEL_ERRORS[code].split(' ', 1)[0]}): {PANEL_ERRORS[code].split(' ', 1)[1]}"
    return f"{code}: {FAULTS.get(code, f'Unknown error {code}')}"


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
        super().__init__(coordinator, entry, description.key)
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


class Ppe4ErrorSensor(Ppe4Entity, SensorEntity):
    """All active heater errors in one sensor.

    The state is ``OK`` when no error is reported, otherwise the decoded
    ``code: text`` pairs joined with ``; ``.  The attributes always contain the
    full decoded list (with Polish texts) and the raw register values, so a
    fault is visible even when the state string is truncated.
    """

    _attr_translation_key = "error"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: Ppe4Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "error")

    @property
    def native_value(self) -> str | None:
        """Return the active errors as text."""
        if self.coordinator.data is None or self.coordinator.data.error is None:
            return None
        state = self.coordinator.data.error
        if not state.active:
            return "OK"
        parts = [_error_text(code) for code in state.codes]
        parts.extend(f"Unknown code {value}" for value in state.unknown)
        return "; ".join(parts)[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return every decoded error and the raw register values."""
        if self.coordinator.data is None or self.coordinator.data.error is None:
            return None
        state = self.coordinator.data.error
        config = self.coordinator.error_config
        return {
            "errors": [
                {
                    "code": code,
                    "panel_code": f"E{code:02d}" if code in PANEL_ERRORS else None,
                    "panel_text": PANEL_ERRORS.get(code),
                    "text": FAULTS.get(code, f"Unknown error {code}"),
                    "text_pl": FAULTS_PL.get(code, ""),
                }
                for code in state.codes
            ],
            "unknown_values": list(state.unknown),
            "registers": {str(register): value for register, value in state.values.items()},
            "error_registers": list(config.registers) if config else [],
            "encoding": config.encoding if config else None,
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
    entities.append(Ppe4ErrorSensor(coordinator, entry))
    async_add_entities(entities)
