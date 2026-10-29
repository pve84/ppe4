"""Base entity for the KOSPEL PPE4 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, MANUFACTURER, MODEL
from .coordinator import Ppe4Coordinator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry


class Ppe4Entity(CoordinatorEntity[Ppe4Coordinator]):
    """Base class for all PPE4 entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: Ppe4Coordinator, entry: ConfigEntry, unique_key: str
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=DEFAULT_NAME,
            configuration_url=coordinator.client.base_url,
        )
