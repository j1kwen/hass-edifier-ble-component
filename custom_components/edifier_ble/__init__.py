"""The Edifier BLE integration."""

from __future__ import annotations

import logging

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    async_ble_device_from_address,
    async_last_service_info,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_CONNECTION_ENABLED,
    CONF_MODEL,
    DEFAULT_CONNECTION_ENABLED,
    DOMAIN,
    model_from_model_code,
)
from .coordinator import EdifierCoordinator
from .device import EdifierDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Edifier BLE device from a config entry."""
    address = entry.unique_id or entry.data.get(CONF_ADDRESS)
    if not address:
        raise ConfigEntryNotReady("Config entry has no Bluetooth address")

    model = model_from_model_code(entry.data.get(CONF_MODEL))
    if model is None:
        raise ConfigEntryNotReady("Unknown Edifier device model")

    def _fresh_device_callback() -> BLEDevice | None:
        """Return the most recent connectable BLEDevice known to HA."""
        if service_info := async_last_service_info(
            hass, address, connectable=True
        ):
            return service_info.device
        return async_ble_device_from_address(hass, address, connectable=True)

    device = EdifierDevice(address, model, _fresh_device_callback)
    coordinator = EdifierCoordinator(
        hass,
        _LOGGER,
        entry=entry,
        address=address,
        mode=BluetoothScanningMode.ACTIVE,
        device=device,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    connection_enabled = entry.options.get(
        CONF_CONNECTION_ENABLED, DEFAULT_CONNECTION_ENABLED
    )
    if connection_enabled:
        if service_info := async_last_service_info(hass, address, connectable=True):
            device.update_advertisement(service_info.rssi)
        ble_device = _fresh_device_callback()
        if ble_device is None:
            hass.data[DOMAIN].pop(entry.entry_id, None)
            raise ConfigEntryNotReady(
                f"Connectable Bluetooth device {address} was not found"
            )

        try:
            await coordinator.async_initialize(ble_device)
        except (BleakError, TimeoutError, EOFError) as err:
            await device.async_disconnect()
            hass.data[DOMAIN].pop(entry.entry_id, None)
            raise ConfigEntryNotReady(
                f"Unable to initialize Edifier device {address}: {err}"
            ) from err

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Edifier BLE config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: EdifierCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
