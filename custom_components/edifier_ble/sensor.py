"""Sensor platform for Edifier BLE."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EdifierBluetoothDataProcessor, EdifierCoordinator
from .entity import (
    SENSOR_DESCRIPTIONS,
    EdifierEntity,
    state_to_bluetooth_data,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Edifier sensors."""
    coordinator: EdifierCoordinator = hass.data[DOMAIN][entry.entry_id]
    processor = EdifierBluetoothDataProcessor(
        lambda state: state_to_bluetooth_data(
            state,
            coordinator.device.model,
            coordinator.address,
            SENSOR_DESCRIPTIONS,
        )
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(EdifierSensor, async_add_entities)
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class EdifierSensor(EdifierEntity, SensorEntity):
    """An Edifier diagnostic sensor."""

    @property
    def native_value(self) -> int | None:
        """Return the sensor value."""
        return self.processor.entity_data.get(self.entity_key)
