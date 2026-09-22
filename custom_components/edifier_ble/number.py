"""Number platform for Edifier BLE."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_VOLUME
from .coordinator import EdifierBluetoothDataProcessor, EdifierCoordinator
from .entity import (
    NUMBER_DESCRIPTIONS,
    EdifierControlEntity,
    state_to_bluetooth_data,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Edifier volume and equalizer numbers."""
    coordinator: EdifierCoordinator = hass.data[DOMAIN][entry.entry_id]
    processor = EdifierBluetoothDataProcessor(
        lambda state: state_to_bluetooth_data(
            state,
            coordinator.device.model,
            coordinator.address,
            NUMBER_DESCRIPTIONS,
        )
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(EdifierNumber, async_add_entities)
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class EdifierNumber(EdifierControlEntity, NumberEntity):
    """An Edifier volume or equalizer band number."""

    @property
    def available(self) -> bool:
        """Return whether this number can currently be controlled."""
        if not super().available:
            return False
        if getattr(self.entity_description, "eq_diy_only", False):
            return self.coordinator.device.state.eq_mode == "diy"
        return True

    @property
    def native_value(self) -> float | None:
        """Return the number value."""
        return self.processor.entity_data.get(self.entity_key)

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        try:
            if self.entity_description.key == KEY_VOLUME:
                await self.coordinator.device.async_set_volume(round(value))
            else:
                await self.coordinator.device.async_set_eq_band(
                    self.entity_description.key, value
                )
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Unable to set value: {err}") from err
