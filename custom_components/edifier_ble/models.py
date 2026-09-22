"""Data models for the Edifier BLE integration."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_MAX_DEVICE_NAME_LENGTH = 248


@dataclass(frozen=True, slots=True)
class EdifierModel:
    """A supported Edifier device model."""

    service_uuid: str
    model: str
    model_code: str
    manufacturer: str

@dataclass(slots=True)
class EdifierFeatures:
    """Features decoded from the D8 response."""

    flags: dict[str, bool] = field(default_factory=dict)
    max_device_name_length: int = DEFAULT_MAX_DEVICE_NAME_LENGTH

    def supports(self, feature: str) -> bool:
        """Return if a named feature is supported."""
        return self.flags.get(feature, False)

@dataclass(slots=True)
class EdifierState:
    """Current state of a connected Edifier device."""

    device_name: str | None = None
    firmware_version: str | None = None
    mac_address: str | None = None
    source: str | None = None
    volume: int | None = None
    eq_mode: str | None = None
    eq_bands: dict[str, float] = field(default_factory=dict)
    light_time: str | None = None
    light_distance: str | None = None
    beep: bool | None = None
    rssi: int | None = None
    playing: bool | None = None
    media_title: str | None = None
    media_artist: str | None = None
    connected: bool = False
    features: EdifierFeatures = field(default_factory=EdifierFeatures)

@dataclass(frozen=True, slots=True)
class EdifierMediaState:
    """Media player state passed to the media player entity."""

    state: str
    volume: int | None
    muted: bool
    title: str | None
    artist: str | None
    source: str | None
