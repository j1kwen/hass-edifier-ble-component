"""Switch platform for Edifier BLE."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_BEEP, KEY_CONNECTION
from .coordinator import EdifierBluetoothDataProcessor, EdifierCoordinator
from .entity import (
    SWITCH_DESCRIPTIONS,
    EdifierControlEntity,
    build_device_info,
    state_to_bluetooth_data,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BLE connection switch and Edifier switches."""
    coordinator: EdifierCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EdifierConnectionSwitch(coordinator)])

    processor = EdifierBluetoothDataProcessor(
        lambda state: state_to_bluetooth_data(
            state,
            coordinator.device.model,
            coordinator.address,
            SWITCH_DESCRIPTIONS,
        )
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(EdifierBeepSwitch, async_add_entities)
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class EdifierConnectionSwitch(SwitchEntity):
    """Control whether Home Assistant keeps the BLE control channel connected."""

    _attr_has_entity_name = True
    _attr_translation_key = KEY_CONNECTION
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: EdifierCoordinator) -> None:
        """Initialize the connection switch."""
        super().__init__()
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}-{KEY_CONNECTION}"
        self._attr_device_info = build_device_info(
            coordinator.address, coordinator.device.model, coordinator.device.state
        )

    @property
    def available(self) -> bool:
        """The switch remains available so the connection can be restored."""
        return True

    @property
    def is_on(self) -> bool:
        """Return if the Home Assistant connection is enabled."""
        return self.coordinator.connection_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the Home Assistant BLE connection."""
        try:
            await self.coordinator.async_set_connection_enabled(True)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Unable to connect to the device: {err}") from err
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the Home Assistant BLE connection."""
        await self.coordinator.async_set_connection_enabled(False)
        self.async_write_ha_state()


class EdifierBeepSwitch(EdifierControlEntity, SwitchEntity):
    """The Bluetooth prompt-tone switch."""

    @property
    def is_on(self) -> bool | None:
        """Return if prompt tones are enabled."""
        return self.processor.entity_data.get(self.entity_key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable prompt tones."""
        await self.coordinator.device.async_set_beep(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable prompt tones."""
        await self.coordinator.device.async_set_beep(False)
