"""Text platform for Edifier BLE."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EdifierBluetoothDataProcessor, EdifierCoordinator
from .entity import (
    TEXT_DESCRIPTIONS,
    EdifierControlEntity,
    state_to_bluetooth_data,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Edifier device name text entity."""
    coordinator: EdifierCoordinator = hass.data[DOMAIN][entry.entry_id]
    processor = EdifierBluetoothDataProcessor(
        lambda state: state_to_bluetooth_data(
            state,
            coordinator.device.model,
            coordinator.address,
            TEXT_DESCRIPTIONS,
        )
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(EdifierText, async_add_entities)
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class EdifierText(EdifierControlEntity, TextEntity):
    """The configurable Edifier device name."""

    @property
    def native_max(self) -> int:
        """Return the dynamic maximum name length from D8."""
        return self.coordinator.device.max_device_name_length

    @property
    def native_value(self) -> str | None:
        """Return the device name."""
        return self.processor.entity_data.get(self.entity_key)

    async def async_set_value(self, value: str) -> None:
        """Set the device name."""
        try:
            await self.coordinator.device.async_set_device_name(value)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Unable to set device name: {err}") from err
