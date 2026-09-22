"""Media player platform for Edifier BLE."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EdifierBluetoothDataProcessor, EdifierCoordinator
from .entity import (
    MEDIA_PLAYER_DESCRIPTIONS,
    EdifierControlEntity,
    state_to_bluetooth_data,
)
from .models import EdifierMediaState

SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Edifier media player."""
    coordinator: EdifierCoordinator = hass.data[DOMAIN][entry.entry_id]
    processor = EdifierBluetoothDataProcessor(
        lambda state: state_to_bluetooth_data(
            state,
            coordinator.device.model,
            coordinator.address,
            MEDIA_PLAYER_DESCRIPTIONS,
        )
    )
    entry.async_on_unload(
        processor.async_add_entities_listener(EdifierMediaPlayer, async_add_entities)
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class EdifierMediaPlayer(EdifierControlEntity, MediaPlayerEntity):
    """Control Edifier playback, volume, and media metadata."""

    _attr_supported_features = SUPPORTED_FEATURES
    _attr_volume_step = 1 / 16

    @property
    def _media(self) -> EdifierMediaState | None:
        """Return the current media state."""
        return self.processor.entity_data.get(self.entity_key)

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the playback state."""
        if (media := self._media) is None:
            return None
        try:
            return MediaPlayerState(media.state)
        except ValueError:
            return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        """Return volume as a 0..1 value."""
        if (media := self._media) is None or media.volume is None:
            return None
        return media.volume / 16

    @property
    def is_volume_muted(self) -> bool | None:
        """Return if the device is muted."""
        if (media := self._media) is None:
            return None
        return media.muted

    @property
    def media_title(self) -> str | None:
        """Return the current track title."""
        return self._media.title if self._media else None

    @property
    def media_artist(self) -> str | None:
        """Return the current track artist."""
        return self._media.artist if self._media else None

    @property
    def source(self) -> str | None:
        """Return the active source."""
        return self._media.source if self._media else None

    async def async_turn_on(self) -> None:
        """Start playback."""
        await self.coordinator.device.async_play_control("play")

    async def async_turn_off(self) -> None:
        """Pause playback."""
        await self.coordinator.device.async_play_control("pause")

    async def async_play(self) -> None:
        """Start playback."""
        await self.coordinator.device.async_play_control("play")

    async def async_pause(self) -> None:
        """Pause playback."""
        await self.coordinator.device.async_play_control("pause")

    async def async_media_next_track(self) -> None:
        """Skip to the next track."""
        await self.coordinator.device.async_play_control("next")

    async def async_media_previous_track(self) -> None:
        """Return to the previous track."""
        await self.coordinator.device.async_play_control("previous")

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume from 0..1."""
        await self.coordinator.device.async_set_volume(round(volume * 16))

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or restore volume."""
        await self.coordinator.device.async_mute_volume(mute)
