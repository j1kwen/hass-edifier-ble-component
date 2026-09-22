"""Bluetooth coordinator for the Edifier BLE integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.bluetooth.active_update_processor import (
    ActiveBluetoothProcessorCoordinator,
)
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, CoreState, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_CONNECTION_ENABLED,
    DEFAULT_CONNECTION_ENABLED,
    REFRESH_INTERVAL_SECONDS,
)
from .device import EdifierDevice
from .models import EdifierState

_LOGGER = logging.getLogger(__name__)


class EdifierBluetoothDataProcessor(
    PassiveBluetoothDataProcessor[Any, EdifierState]
):
    """Data processor used by Edifier entity platforms."""

    coordinator: EdifierCoordinator

    @callback
    def async_add_entities_listener(
        self,
        entity_class: type[Any],
        async_add_entities: AddEntitiesCallback,
    ) -> Callable[[], None]:
        """Add entities and remove them when their D8 feature disappears."""
        created: dict[PassiveBluetoothEntityKey, Any] = {}
        removing: set[PassiveBluetoothEntityKey] = set()
        cancelled = False
        last_data: PassiveBluetoothDataUpdate[Any] | None = None

        async def _async_remove_entity(
            key: PassiveBluetoothEntityKey, entity: Any
        ) -> None:
            try:
                await entity.async_remove()
            finally:
                removing.discard(key)
                if not cancelled and last_data is not None:
                    _handle_update(last_data)

        @callback
        def _handle_update(data: PassiveBluetoothDataUpdate[Any] | None) -> None:
            nonlocal last_data
            if cancelled or data is None:
                return
            last_data = data
            current_keys = set(data.entity_descriptions)

            entities: list[Any] = []
            for key, description in data.entity_descriptions.items():
                if key in created or key in removing:
                    continue
                entity = entity_class(self, key, description)
                created[key] = entity
                entities.append(entity)
            if entities:
                async_add_entities(entities)

            for key in set(created) - current_keys:
                entity = created.pop(key)
                removing.add(key)
                self.coordinator.hass.async_create_task(
                    _async_remove_entity(key, entity)
                )

        remove_listener = self.async_add_listener(_handle_update)

        @callback
        def _remove_listener() -> None:
            nonlocal cancelled
            cancelled = True
            remove_listener()

        return _remove_listener

    @callback
    def async_handle_update(
        self, update: EdifierState, was_available: bool | None = None
    ) -> None:
        """Handle an update and drop entity descriptions no longer provided."""
        super().async_handle_update(update, was_available)
        try:
            current_data = self.update_method(update)
        except Exception:  # noqa: BLE001
            return

        current_keys = set(current_data.entity_descriptions)
        for key in set(self.data.entity_descriptions) - current_keys:
            self.data.entity_descriptions.pop(key, None)
            self.data.entity_data.pop(key, None)
            self.data.entity_names.pop(key, None)


class EdifierCoordinator(ActiveBluetoothProcessorCoordinator[EdifierState]):
    """Active Bluetooth processor coordinator for an Edifier device."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        entry: ConfigEntry,
        address: str,
        mode: BluetoothScanningMode,
        device: EdifierDevice,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.device = device
        self.connection_enabled = entry.options.get(
            CONF_CONNECTION_ENABLED, DEFAULT_CONNECTION_ENABLED
        )
        self._refresh_lock = asyncio.Lock()
        self._cancel_interval: CALLBACK_TYPE | None = None

        super().__init__(
            hass,
            logger,
            address=address,
            mode=mode,
            update_method=self._update_method,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_poll_device,
            connectable=True,
        )
        device.set_state_changed_callback(self._device_state_changed)

    @property
    def available(self) -> bool:
        """Return if this coordinator is available."""
        return self.connection_enabled and self.device.initialized

    @callback
    def async_register_processor(
        self,
        processor: EdifierBluetoothDataProcessor,
        entity_description_class: type | None = None,
    ) -> Callable[[], None]:
        """Register a data processor and immediately send the current state."""
        # Do not let Home Assistant restore custom platform descriptions.
        # Its restore path converts them to base HA dataclasses and drops
        # integration-specific fields such as feature_keys.
        remove_processor = super().async_register_processor(processor, None)
        processor.async_handle_update(self.device.state)
        return remove_processor

    async def async_initialize(self, ble_device: BLEDevice | None = None) -> None:
        """Connect and run the D8-driven initialization sequence."""
        if not self.connection_enabled:
            return
        await self.device.async_ensure_ready(ble_device)
        self._async_handle_state_update()

    async def async_set_connection_enabled(self, enabled: bool) -> None:
        """Enable or disable the Home Assistant BLE connection."""
        async with self._refresh_lock:
            if enabled:
                try:
                    await self.device.async_ensure_ready()
                except Exception:  # noqa: BLE001
                    await self.device.async_disconnect()
                    raise
                self.connection_enabled = True
            else:
                self.connection_enabled = False
                await self.device.async_disconnect()

        options = dict(self.entry.options)
        options[CONF_CONNECTION_ENABLED] = enabled
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self._async_handle_state_update()

    async def async_shutdown(self) -> None:
        """Shut down the coordinator and its BLE connection."""
        await self.device.async_disconnect()

    @callback
    def _update_method(
        self, service_info: BluetoothServiceInfoBleak
    ) -> EdifierState:
        """Return state for a Bluetooth advertisement event."""
        self.device.update_advertisement(service_info.rssi)
        return self.device.state

    def _needs_poll(
        self, service_info: BluetoothServiceInfoBleak, last_poll: float | None
    ) -> bool:
        """Return if the device should be connected or refreshed."""
        if self.hass.state is not CoreState.running or not self.connection_enabled:
            return False
        if not self.device.connected:
            return True
        return last_poll is None or last_poll >= REFRESH_INTERVAL_SECONDS

    async def _async_poll_device(
        self, service_info: BluetoothServiceInfoBleak
    ) -> EdifierState:
        """Poll the device after an advertisement triggers a refresh."""
        if not self.connection_enabled:
            return self.device.state
        await self._async_refresh_device(service_info.device)
        return self.device.state

    @callback
    def _async_start(self) -> None:
        """Start advertisement tracking and periodic state refresh."""
        super()._async_start()
        self._cancel_interval = async_track_time_interval(
            self.hass,
            self._async_periodic_refresh,
            timedelta(seconds=REFRESH_INTERVAL_SECONDS),
        )

    @callback
    def _async_stop(self) -> None:
        """Stop advertisement tracking and periodic refresh."""
        if self._cancel_interval is not None:
            self._cancel_interval()
            self._cancel_interval = None
        super()._async_stop()

    async def _async_periodic_refresh(self, _: object) -> None:
        """Refresh state periodically while the connection is enabled."""
        if not self.connection_enabled:
            return
        try:
            await self._async_refresh_device()
        except BleakError as err:
            _LOGGER.debug("%s: Periodic refresh failed: %s", self.address, err)
            self._async_handle_state_update()

    async def _async_refresh_device(self, ble_device: BLEDevice | None = None) -> None:
        """Refresh the device while preventing overlapping refreshes."""
        async with self._refresh_lock:
            await self.device.async_refresh(ble_device)
        self._async_handle_state_update()

    def _device_state_changed(self) -> None:
        """Handle a device state change from either the event loop or a BLE thread."""
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is self.hass.loop:
            self._async_handle_state_update()
        else:
            self.hass.loop.call_soon_threadsafe(self._async_handle_state_update)

    @callback
    def _async_handle_state_update(self) -> None:
        """Send the latest complete state to every registered processor."""
        for processor in list(self._processors):
            # Force all known entities to re-evaluate availability when D8,
            # connection state, or any value changes.
            processor.async_handle_update(self.device.state, was_available=False)

