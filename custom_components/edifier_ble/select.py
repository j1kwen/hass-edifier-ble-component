"""Select platform for Edifier BLE."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    KEY_EQ_MODE,
    KEY_LIGHT_DISTANCE,
    KEY_LIGHT_TIME,
    KEY_SOURCE,
)
from .coordinator import EdifierBluetoothDataProcessor, EdifierCoordinator
from .entity import (
    SELECT_DESCRIPTIONS,
    EdifierControlEntity,
    state_to_bluetooth_data,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Edifier select entities."""
    coordinator: EdifierCoordinator = hass.data[DOMAIN][entry.entry_id]
    processor = EdifierBluetoothDataProcessor(
        lambda state: state_to_bluetooth_data(
            state,
            coordinator.device.model,
            coordinator.address,
            SELECT_DESCRIPTIONS,
        )
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(EdifierSelect, async_add_entities)
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class EdifierSelect(EdifierControlEntity, SelectEntity):
    """An Edifier select entity."""

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        return self.processor.entity_data.get(self.entity_key)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        try:
            key = self.entity_description.key
            if key == KEY_SOURCE:
                await self.coordinator.device.async_set_source(option)
            elif key == KEY_EQ_MODE:
                await self.coordinator.device.async_set_eq_mode(option)
            elif key == KEY_LIGHT_TIME:
                await self.coordinator.device.async_set_light(option)
            elif key == KEY_LIGHT_DISTANCE:
                await self.coordinator.device.async_set_light(distance=option)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Unable to select option: {err}") from err
