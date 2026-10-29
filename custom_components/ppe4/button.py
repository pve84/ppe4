"""Button platform for the KOSPEL PPE4 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Ppe4Coordinator
from .entity import Ppe4Entity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from homeassistant.config_entries import ConfigEntry


class Ppe4RefreshButton(Ppe4Entity, ButtonEntity):
    """Force an immediate poll of the heater."""

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: Ppe4Coordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator, entry, "refresh")

    async def async_press(self) -> None:
        """Poll the heater now."""
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the refresh button."""
    coordinator: Ppe4Coordinator = entry.runtime_data
    async_add_entities([Ppe4RefreshButton(coordinator, entry)])
