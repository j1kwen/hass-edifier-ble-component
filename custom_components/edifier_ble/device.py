"""BLE device manager for the Edifier BLE integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakNotFoundError,
    establish_connection,
)

from .const import (
    CMD_GET_DEVICE_NAME,
    CMD_GET_FIRMWARE,
    CMD_GET_MAC,
    CMD_MEDIA_INFO,
    CMD_PLAY_CONTROL,
    CMD_QUERY_BEEP,
    CMD_QUERY_EQ_BANDS,
    CMD_QUERY_EQ_MODE,
    CMD_QUERY_FEATURES,
    CMD_QUERY_LIGHT,
    CMD_QUERY_SOURCE,
    CMD_QUERY_VOLUME,
    CMD_SET_BEEP,
    CMD_SET_DEVICE_NAME,
    CMD_SET_EQ_BAND,
    CMD_SET_EQ_MODE,
    CMD_SET_LIGHT,
    CMD_SET_SOURCE,
    CMD_SET_VOLUME,
    CMD_SOURCE_STATUS,
    COMMAND_TIMEOUT_SECONDS,
    NOTIFY_CHARACTERISTIC_UUID,
    QUERY_TIMEOUT_SECONDS,
    WRITE_CHARACTERISTIC_UUID,
)
from .models import EdifierMediaState, EdifierModel, EdifierState
from .protocol import (
    DISTANCE_TO_OPTION,
    EQ_BANDS_BY_KEY,
    EQ_MODE_TO_OPTION,
    LIGHT_TIME_TO_OPTION,
    OPTION_TO_DISTANCE,
    OPTION_TO_EQ_MODE,
    OPTION_TO_LIGHT_TIME,
    OPTION_TO_SOURCE,
    PLAY_OPTION_TO_COMMAND,
    SOURCE_TO_OPTION,
    EdifierFrame,
    PacketStreamParser,
    build_eq_band_data,
    build_packet,
    parse_d8_features,
    parse_eq_bands,
    parse_firmware_version,
    parse_mac_address,
    parse_media_info,
    parse_utf8,
)

_LOGGER = logging.getLogger(__name__)

StateChangedCallback = Callable[[], None]
FreshDeviceCallback = Callable[[], BLEDevice | None]


class EdifierDevice:
    """Manage a connection and the current state of one Edifier device."""

    def __init__(
        self,
        address: str,
        model: EdifierModel,
        fresh_device_callback: FreshDeviceCallback,
    ) -> None:
        """Initialize the device manager."""
        self.address = address
        self.model = model
        self._fresh_device_callback = fresh_device_callback
        self._client: BleakClientWithServiceCache | None = None
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._pending: dict[int, list[asyncio.Future[bytes]]] = {}
        self._stream_parser = PacketStreamParser()
        self._state = EdifierState()
        self._initialized = False
        self._state_changed_callback: StateChangedCallback | None = None
        self._last_nonzero_volume: int | None = None

    @property
    def state(self) -> EdifierState:
        """Return the current state."""
        return self._state

    @property
    def connected(self) -> bool:
        """Return if the BLE client is connected."""
        client = self._client
        return bool(client is not None and client.is_connected)

    @property
    def initialized(self) -> bool:
        """Return if D8 and the supported state queries have completed."""
        return self._initialized and self.connected

    @property
    def last_nonzero_volume(self) -> int:
        """Return the last non-zero volume, defaulting to half volume."""
        return self._last_nonzero_volume or 8

    @property
    def max_device_name_length(self) -> int:
        """Return the dynamic maximum device name length in bytes."""
        return self._state.features.max_device_name_length

    def set_state_changed_callback(self, callback: StateChangedCallback) -> None:
        """Set the callback invoked after state or connection changes."""
        self._state_changed_callback = callback

    def update_advertisement(self, rssi: int | None) -> None:
        """Update RSSI from a Bluetooth advertisement without notifying listeners."""
        if rssi is not None:
            self._state.rssi = rssi

    def _notify_state_changed(self) -> None:
        """Notify the coordinator that state changed."""
        if self._state_changed_callback is not None:
            self._state_changed_callback()

    async def async_connect(self, ble_device: BLEDevice | None = None) -> bool:
        """Connect to the device and subscribe to notifications.

        Returns True when a new connection was established.
        """
        async with self._connect_lock:
            if self.connected:
                return False

            device = ble_device or self._fresh_device_callback()
            if device is None:
                raise BleakNotFoundError(
                    f"No connectable Bluetooth device found for {self.address}"
                )

            def _disconnected(disconnected_client: BleakClientWithServiceCache) -> None:
                """Handle a BLE disconnect callback."""
                if self._client is not disconnected_client:
                    return
                self._client = None
                self._initialized = False
                self._state.connected = False
                self._fail_pending(BleakError("Bluetooth device disconnected"))
                self._notify_state_changed()

            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                self._device_name,
                disconnected_callback=_disconnected,
                max_attempts=4,
            )

            try:
                await client.start_notify(
                    NOTIFY_CHARACTERISTIC_UUID, self._notification_handler
                )
            except BleakError:
                await client.disconnect()
                raise

            self._client = client
            self._stream_parser = PacketStreamParser()
            self._state.connected = True
            self._notify_state_changed()
            _LOGGER.debug("%s: connected", self.address)
            return True

    async def async_disconnect(self) -> None:
        """Disconnect the BLE client."""
        async with self._connect_lock:
            client = self._client
            self._client = None
            self._initialized = False
            self._state.connected = False
            self._fail_pending(BleakError("Bluetooth device disconnected"))

            if client is not None:
                try:
                    await client.stop_notify(NOTIFY_CHARACTERISTIC_UUID)
                except (BleakError, EOFError, BrokenPipeError):
                    pass
                try:
                    await client.disconnect()
                except (BleakError, EOFError, BrokenPipeError):
                    pass

            self._notify_state_changed()
            _LOGGER.debug("%s: disconnected", self.address)

    async def async_ensure_ready(self, ble_device: BLEDevice | None = None) -> None:
        """Ensure the device is connected, initialized, and state is refreshed."""
        new_connection = await self.async_connect(ble_device)
        if new_connection or not self._initialized:
            await self.async_initialize()
        else:
            await self.async_query_all()

    async def async_initialize(self) -> None:
        """Query D8 and then refresh all supported state."""
        if not self.connected:
            raise BleakError("Device is not connected")

        await self._async_query(CMD_QUERY_FEATURES, timeout=QUERY_TIMEOUT_SECONDS)
        if not self._state.features.flags:
            raise BleakError("Device returned an empty D8 feature bitmap")

        await self.async_query_all()
        self._initialized = True
        self._notify_state_changed()

    async def async_refresh(self, ble_device: BLEDevice | None = None) -> None:
        """Refresh the connection and all supported state."""
        await self.async_ensure_ready(ble_device)

    async def async_query_all(self) -> None:
        """Query all state supported by the current D8 feature bitmap."""
        features = self._state.features
        requests: list[tuple[int, bytes]] = []

        if features.supports("GetDeviceName"):
            requests.append((CMD_GET_DEVICE_NAME, b""))
        if features.supports("GetMacAddress"):
            requests.append((CMD_GET_MAC, b""))
        if features.supports("GetFirmwareVersion"):
            requests.append((CMD_GET_FIRMWARE, b""))
        if features.supports("InputSourceSettings"):
            requests.append((CMD_QUERY_SOURCE, b""))
        if features.supports("VolumeSettings"):
            requests.append((CMD_QUERY_VOLUME, b""))
        if features.supports("Equalizer"):
            requests.append((CMD_QUERY_EQ_MODE, b""))
            requests.append((CMD_QUERY_EQ_BANDS, b""))
        if features.supports("SmartLight"):
            requests.append((CMD_QUERY_LIGHT, b""))
        if features.supports("BeepSet"):
            requests.append((CMD_QUERY_BEEP, b""))

        if not requests:
            return

        # Wait for each response before sending the next query. Using the
        # response as flow control is more reliable than flooding a device
        # with multiple write-without-response requests.
        for command, data in requests:
            try:
                await self._async_query(
                    command, data, timeout=QUERY_TIMEOUT_SECONDS
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "%s: Query command 0x%02X did not complete: %s",
                    self.address,
                    command,
                    err,
                )

    async def _async_query(
        self, command: int, data: bytes = b"", timeout: float = QUERY_TIMEOUT_SECONDS
    ) -> bytes:
        """Send a query and wait for its response."""
        try:
            return await self._async_send_and_wait(command, data, timeout)
        except TimeoutError as err:
            raise BleakError(
                f"Timed out waiting for response to command 0x{command:02X}"
            ) from err

    async def _async_send_command(
        self,
        command: int,
        data: bytes = b"",
        timeout: float = COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        """Send a command and wait briefly for an optional acknowledgement."""
        try:
            await self._async_send_and_wait(command, data, timeout)
        except TimeoutError:
            _LOGGER.debug(
                "%s: Command 0x%02X sent without a response",
                self.address,
                command,
            )

    async def _async_send_and_wait(
        self, command: int, data: bytes, timeout: float
    ) -> bytes:
        """Send a packet and wait for a matching notification."""
        if command in (0xCE, 0xCF):
            raise ValueError("Unsafe Edifier command blocked")

        async with self._write_lock:
            client = self._client
            if client is None or not client.is_connected:
                raise BleakError("Device is not connected")

            loop = asyncio.get_running_loop()
            future: asyncio.Future[bytes] = loop.create_future()
            self._pending.setdefault(command, []).append(future)

            try:
                await client.write_gatt_char(
                    WRITE_CHARACTERISTIC_UUID,
                    build_packet(command, data),
                    response=False,
                )
            except Exception:
                self._remove_pending(command, future)
                raise

        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            raise
        finally:
            self._remove_pending(command, future)

    def _remove_pending(
        self, command: int, future: asyncio.Future[bytes]
    ) -> None:
        """Remove a pending response future."""
        pending = self._pending.get(command)
        if not pending:
            return
        if future in pending:
            pending.remove(future)
        if not pending:
            self._pending.pop(command, None)

    def _fail_pending(self, exception: Exception) -> None:
        """Fail all pending response futures."""
        for pending in self._pending.values():
            for future in pending:
                if not future.done():
                    future.set_exception(exception)
        self._pending.clear()

    def _notification_handler(
        self, _: object, data: bytearray
    ) -> None:
        """Handle an incoming BLE notification."""
        frames = self._stream_parser.feed(bytes(data))
        if not frames:
            _LOGGER.debug(
                "%s: Ignored malformed notification: %s",
                self.address,
                bytes(data).hex(" "),
            )
            return

        for frame in frames:
            self._update_state(frame)
            self._resolve_pending(frame.command, frame.data)

        self._notify_state_changed()

    def _resolve_pending(self, command: int, data: bytes) -> None:
        """Resolve pending response futures for a command."""
        for future in self._pending.get(command, ()):
            if not future.done():
                future.set_result(data)

    def _update_state(self, frame: EdifierFrame) -> None:
        """Update state from a response frame."""
        command = frame.command
        data = frame.data
        state = self._state

        if command == CMD_GET_FIRMWARE:
            if version := parse_firmware_version(data):
                state.firmware_version = version
        elif command == CMD_GET_MAC:
            if mac_address := parse_mac_address(data):
                state.mac_address = mac_address
        elif command == CMD_GET_DEVICE_NAME:
            state.device_name = parse_utf8(data)
        elif command == CMD_SET_DEVICE_NAME:
            # The setter applies the requested value optimistically.
            pass
        elif command == CMD_QUERY_SOURCE and len(data) >= 2 and data[0] == 0x0F:
            state.source = SOURCE_TO_OPTION.get(data[1], state.source)
        elif command == CMD_SOURCE_STATUS and data:
            if data[0] == 0x05:
                state.source = "aux"
            elif data[0] == 0x00:
                state.source = (
                    state.source
                    if state.source in ("bluetooth", "soundcard")
                    else "bluetooth"
                )
        elif command in (CMD_QUERY_VOLUME, CMD_SET_VOLUME):
            if len(data) >= 2 and data[0] == 0x10:
                self._set_volume_from_device(data[1])
        elif command in (CMD_QUERY_LIGHT, CMD_SET_LIGHT):
            if len(data) >= 3 and data[0] == 0x03:
                state.light_time = LIGHT_TIME_TO_OPTION.get(data[1])
                state.light_distance = DISTANCE_TO_OPTION.get(data[2])
        elif command == CMD_QUERY_BEEP:
            if len(data) >= 2 and data[0] == 0x02:
                state.beep = data[1] == 0x01
        elif command == CMD_SET_BEEP:
            if data:
                state.beep = data[-1] == 0x01
        elif command == CMD_QUERY_EQ_MODE and len(data) == 1:
            state.eq_mode = EQ_MODE_TO_OPTION.get(data[0])
        elif command == CMD_SET_EQ_MODE and len(data) == 1:
            state.eq_mode = EQ_MODE_TO_OPTION.get(data[0], state.eq_mode)
        elif command == CMD_QUERY_EQ_BANDS:
            if gains := parse_eq_bands(data):
                state.eq_bands.update(gains)
        elif command == CMD_MEDIA_INFO:
            playing, title, artist = parse_media_info(data)
            state.playing = playing
            state.media_title = title
            state.media_artist = artist
        elif command == CMD_PLAY_CONTROL and len(data) == 1:
            if data[0] == PLAY_OPTION_TO_COMMAND["play"]:
                state.playing = True
            elif data[0] == PLAY_OPTION_TO_COMMAND["pause"]:
                state.playing = False
        elif command == CMD_QUERY_FEATURES:
            state.features = parse_d8_features(data)
            self._sync_features_to_state()

    def _set_volume_from_device(self, volume: int) -> None:
        """Update volume and remember the last non-zero value."""
        if not 0 <= volume <= 16:
            return
        self._state.volume = volume
        if volume > 0:
            self._last_nonzero_volume = volume

    def _sync_features_to_state(self) -> None:
        """Clear state for features no longer present in D8."""
        features = self._state.features
        state = self._state

        if not features.supports("GetDeviceName"):
            state.device_name = None
        if not features.supports("GetMacAddress"):
            state.mac_address = None
        if not features.supports("GetFirmwareVersion"):
            state.firmware_version = None
        if not features.supports("InputSourceSettings"):
            state.source = None
        if not features.supports("VolumeSettings"):
            state.volume = None
        if not features.supports("Equalizer"):
            state.eq_mode = None
            state.eq_bands.clear()
        if not features.supports("SmartLight"):
            state.light_time = None
            state.light_distance = None
        if not features.supports("BeepSet"):
            state.beep = None
        if not features.supports("MusicInfo"):
            state.playing = None
            state.media_title = None
            state.media_artist = None

    async def async_set_source(self, option: str) -> None:
        """Set the active input source."""
        source = OPTION_TO_SOURCE.get(option)
        if source is None:
            raise ValueError(f"Unsupported source: {option}")
        await self._async_send_command(CMD_SET_SOURCE, bytes((0x0F, source)))
        self._state.source = option
        self._notify_state_changed()

    async def async_set_volume(self, volume: int) -> None:
        """Set volume from 0 to 16, where 0 is mute."""
        if not 0 <= volume <= 16:
            raise ValueError("Volume must be between 0 and 16")
        await self._async_send_command(CMD_SET_VOLUME, bytes((volume,)))
        self._set_volume_from_device(volume)
        self._notify_state_changed()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or restore the last non-zero volume."""
        if mute:
            await self.async_set_volume(0)
        else:
            await self.async_set_volume(self.last_nonzero_volume)

    async def async_set_eq_mode(self, option: str) -> None:
        """Set the equalizer preset."""
        mode = OPTION_TO_EQ_MODE.get(option)
        if mode is None:
            raise ValueError(f"Unsupported equalizer mode: {option}")
        await self._async_send_command(CMD_SET_EQ_MODE, bytes((mode,)))
        self._state.eq_mode = option
        self._notify_state_changed()

    async def async_set_eq_band(self, key: str, gain_db: float) -> None:
        """Set one equalizer band gain in dB."""
        band = EQ_BANDS_BY_KEY.get(key)
        if band is None:
            raise ValueError(f"Unsupported equalizer band: {key}")
        if self._state.eq_mode != "diy":
            raise ValueError("Equalizer bands can only be changed in DIY mode")
        if not -3.0 <= gain_db <= 3.0:
            raise ValueError("Equalizer gain must be between -3.0 and 3.0 dB")
        await self._async_send_command(CMD_SET_EQ_BAND, build_eq_band_data(band, gain_db))
        self._state.eq_bands[key] = round(gain_db * 2) / 2
        self._notify_state_changed()

    async def async_set_light(
        self, option: str | None = None, *, distance: str | None = None
    ) -> None:
        """Set the light duration and/or sensor distance."""
        if option is not None:
            light_time = OPTION_TO_LIGHT_TIME.get(option)
            if light_time is None:
                raise ValueError(f"Unsupported light duration: {option}")
        else:
            light_time = OPTION_TO_LIGHT_TIME.get(
                self._state.light_time or "5s", 0x00
            )

        if distance is not None:
            distance_code = OPTION_TO_DISTANCE.get(distance)
            if distance_code is None:
                raise ValueError(f"Unsupported sensor distance: {distance}")
        else:
            distance_code = OPTION_TO_DISTANCE.get(
                self._state.light_distance or "normal", 0x01
            )

        await self._async_send_command(
            CMD_SET_LIGHT, bytes((0x03, light_time, distance_code))
        )
        self._state.light_time = (
            option if option is not None else self._state.light_time
        )
        self._state.light_distance = (
            distance if distance is not None else self._state.light_distance
        )
        self._notify_state_changed()

    async def async_set_beep(self, enabled: bool) -> None:
        """Enable or disable Bluetooth prompt tones."""
        value = 0x01 if enabled else 0x00
        await self._async_send_command(CMD_SET_BEEP, bytes((0x02, 0x01, value)))
        self._state.beep = enabled
        self._notify_state_changed()

    async def async_set_device_name(self, device_name: str) -> None:
        """Set the device name using the D8-provided byte limit."""
        encoded_name = device_name.encode("utf-8")
        if len(encoded_name) > self.max_device_name_length:
            raise ValueError(
                f"Device name is {len(encoded_name)} bytes; "
                f"the device supports {self.max_device_name_length} bytes"
            )
        await self._async_send_command(CMD_SET_DEVICE_NAME, encoded_name)
        self._state.device_name = device_name
        self._notify_state_changed()

    async def async_play_control(self, action: str) -> None:
        """Send a play, pause, next, or previous command."""
        command = PLAY_OPTION_TO_COMMAND.get(action)
        if command is None:
            raise ValueError(f"Unsupported play control action: {action}")
        await self._async_send_command(CMD_PLAY_CONTROL, bytes((command,)))
        if action == "play":
            self._state.playing = True
        elif action == "pause":
            self._state.playing = False
        self._notify_state_changed()

    @property
    def media_state(self) -> EdifierMediaState:
        """Return the current media player state."""
        state = self._state
        if state.playing is True:
            media_state = "playing"
        elif state.playing is False:
            media_state = "paused"
        else:
            media_state = "idle"
        return EdifierMediaState(
            state=media_state,
            volume=state.volume,
            muted=state.volume == 0,
            title=state.media_title,
            artist=state.media_artist,
            source=state.source,
        )

    @property
    def _device_name(self) -> str:
        """Return a name suitable for BLE connection logging."""
        return f"Edifier {self.model.model} ({self.address})"
