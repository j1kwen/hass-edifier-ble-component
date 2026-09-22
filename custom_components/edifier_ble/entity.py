"""Entity descriptions and base classes for Edifier BLE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntityDescription,
)
from homeassistant.components.number import NumberEntityDescription, NumberMode
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.text import TextEntityDescription
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
)
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo

from .const import (
    DOMAIN,
    KEY_AUDIO_MAC_ADDRESS,
    KEY_BEEP,
    KEY_DEVICE_NAME,
    KEY_CONNECTION_STATUS,
    KEY_EQ_MODE,
    KEY_LIGHT_DISTANCE,
    KEY_LIGHT_TIME,
    KEY_MEDIA_PLAYER,
    KEY_RSSI,
    KEY_SOURCE,
    KEY_VOLUME,
)
from .coordinator import EdifierBluetoothDataProcessor, EdifierCoordinator
from .models import EdifierMediaState, EdifierModel, EdifierState
from .protocol import (
    DISTANCE_TO_OPTION,
    EQ_BANDS,
    EQ_MODE_TO_OPTION,
    LIGHT_TIME_TO_OPTION,
    SOURCE_TO_OPTION,
)


@dataclass(frozen=True, kw_only=True)
class EdifierSensorDescription(SensorEntityDescription):
    """Sensor description with a required D8 feature list."""

    feature_keys: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EdifierBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description with a required D8 feature list."""

    feature_keys: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EdifierTextDescription(TextEntityDescription):
    """Text description with a required D8 feature list."""

    feature_keys: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EdifierNumberDescription(NumberEntityDescription):
    """Number description with a required D8 feature list."""

    feature_keys: tuple[str, ...] = ()
    eq_diy_only: bool = False


@dataclass(frozen=True, kw_only=True)
class EdifierSelectDescription(SelectEntityDescription):
    """Select description with a required D8 feature list."""

    feature_keys: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EdifierSwitchDescription(SwitchEntityDescription):
    """Switch description with a required D8 feature list."""

    feature_keys: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EdifierMediaPlayerDescription(MediaPlayerEntityDescription):
    """Media player description with a required D8 feature list."""

    feature_keys: tuple[str, ...] = ()


SENSOR_DESCRIPTIONS: tuple[EdifierSensorDescription, ...] = (
    EdifierSensorDescription(
        key=KEY_RSSI,
        translation_key="rssi",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        icon="mdi:signal",
    ),
    EdifierSensorDescription(
        key=KEY_AUDIO_MAC_ADDRESS,
        translation_key="audio_mac_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:bluetooth-audio",
        feature_keys=("GetMacAddress",),
    ),
)

BINARY_SENSOR_DESCRIPTIONS: tuple[EdifierBinarySensorDescription, ...] = (
    EdifierBinarySensorDescription(
        key=KEY_CONNECTION_STATUS,
        translation_key="connection_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth",
    ),
)

TEXT_DESCRIPTIONS: tuple[EdifierTextDescription, ...] = (
    EdifierTextDescription(
        key=KEY_DEVICE_NAME,
        translation_key="device_name",
        icon="mdi:rename-box",
        feature_keys=("GetDeviceName", "SetDeviceName"),
    ),
)

NUMBER_DESCRIPTIONS: tuple[EdifierNumberDescription, ...] = (
    EdifierNumberDescription(
        key=KEY_VOLUME,
        translation_key="volume",
        icon="mdi:volume-high",
        native_min_value=0,
        native_max_value=16,
        native_step=1,
        mode=NumberMode.SLIDER,
        feature_keys=("VolumeSettings",),
    ),
    *(
        EdifierNumberDescription(
            key=band.key,
            translation_key=band.key,
            icon="mdi:equalizer",
            native_min_value=-3.0,
            native_max_value=3.0,
            native_step=0.5,
            native_unit_of_measurement="dB",
            mode=NumberMode.SLIDER,
            feature_keys=("Equalizer",),
            eq_diy_only=True,
        )
        for band in EQ_BANDS
    ),
)

SELECT_DESCRIPTIONS: tuple[EdifierSelectDescription, ...] = (
    EdifierSelectDescription(
        key=KEY_SOURCE,
        translation_key="source",
        icon="mdi:audio-input-stereo-minijack",
        options=list(SOURCE_TO_OPTION.values()),
        feature_keys=("InputSourceSettings",),
    ),
    EdifierSelectDescription(
        key=KEY_EQ_MODE,
        translation_key="eq_mode",
        icon="mdi:equalizer",
        options=list(EQ_MODE_TO_OPTION.values()),
        feature_keys=("Equalizer",),
    ),
    EdifierSelectDescription(
        key=KEY_LIGHT_TIME,
        translation_key="light_time",
        icon="mdi:timer-outline",
        options=list(LIGHT_TIME_TO_OPTION.values()),
        feature_keys=("SmartLight",),
    ),
    EdifierSelectDescription(
        key=KEY_LIGHT_DISTANCE,
        translation_key="light_distance",
        icon="mdi:motion-sensor",
        options=list(DISTANCE_TO_OPTION.values()),
        feature_keys=("SmartLight",),
    ),
)

SWITCH_DESCRIPTIONS: tuple[EdifierSwitchDescription, ...] = (
    EdifierSwitchDescription(
        key=KEY_BEEP,
        translation_key="beep",
        icon="mdi:bullhorn",
        feature_keys=("BeepSet",),
    ),
)

MEDIA_PLAYER_DESCRIPTIONS: tuple[EdifierMediaPlayerDescription, ...] = (
    EdifierMediaPlayerDescription(
        key=KEY_MEDIA_PLAYER,
        translation_key="media_player",
        icon="mdi:speaker",
        device_class=MediaPlayerDeviceClass.SPEAKER,
        feature_keys=("VolumeSettings", "MusicInfo"),
    ),
)


def build_device_info(
    address: str, model: EdifierModel, state: EdifierState
) -> DeviceInfo:
    """Build Home Assistant device information from the latest state."""
    identifiers = {(DOMAIN, address)}
    if state.mac_address and state.mac_address != address:
        # Keep the audio MAC as a secondary identifier so existing device
        # registry entries can migrate without creating a duplicate device.
        identifiers.add((DOMAIN, state.mac_address))

    return DeviceInfo(
        identifiers=identifiers,
        connections={(CONNECTION_BLUETOOTH, address)},
        name=state.device_name or f"{model.manufacturer} {model.model}",
        manufacturer=model.manufacturer,
        model=model.model,
        sw_version=state.firmware_version,
    )


def state_to_bluetooth_data(
    state: EdifierState,
    model: EdifierModel,
    address: str,
    descriptions: tuple[Any, ...],
) -> PassiveBluetoothDataUpdate[Any]:
    """Convert the complete device state into processor data."""
    update: PassiveBluetoothDataUpdate[Any] = PassiveBluetoothDataUpdate(
        devices={None: build_device_info(address, model, state)}
    )

    for description in descriptions:
        feature_keys: tuple[str, ...] = getattr(description, "feature_keys", ())
        if not all(state.features.supports(feature) for feature in feature_keys):
            continue

        entity_key = PassiveBluetoothEntityKey(description.key, None)
        update.entity_descriptions[entity_key] = description
        update.entity_data[entity_key] = _entity_value(state, description.key)

    return update


def _entity_value(state: EdifierState, key: str) -> Any:
    """Return the value for an entity key."""
    if key == KEY_DEVICE_NAME:
        return state.device_name
    if key == KEY_VOLUME:
        return state.volume
    if key == KEY_SOURCE:
        return state.source
    if key == KEY_EQ_MODE:
        return state.eq_mode
    if key == KEY_LIGHT_TIME:
        return state.light_time
    if key == KEY_LIGHT_DISTANCE:
        return state.light_distance
    if key == KEY_BEEP:
        return state.beep
    if key == KEY_RSSI:
        return state.rssi
    if key == KEY_AUDIO_MAC_ADDRESS:
        return state.mac_address
    if key == KEY_CONNECTION_STATUS:
        return state.connected
    if key == KEY_MEDIA_PLAYER:
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
    return state.eq_bands.get(key)


class EdifierEntity(
    PassiveBluetoothProcessorEntity[EdifierBluetoothDataProcessor]
):
    """Base entity for Edifier processor-backed entities."""

    coordinator: EdifierCoordinator

    def __init__(self, processor: Any, entity_key: Any, description: Any) -> None:
        """Initialize the entity."""
        super().__init__(processor, entity_key, description)
        self.coordinator = processor.coordinator
        self._attr_device_info = build_device_info(
            self.coordinator.address,
            self.coordinator.device.model,
            self.coordinator.device.state,
        )

    def _handle_processor_update(self, new_data: Any) -> None:
        """Refresh device information before writing entity state."""
        self._attr_device_info = build_device_info(
            self.coordinator.address,
            self.coordinator.device.model,
            self.coordinator.device.state,
        )
        super()._handle_processor_update(new_data)

    @property
    def available(self) -> bool:
        """Return if the entity is available and still supported by D8."""
        description = cast(Any, self.entity_description)
        return self.processor.last_update_success and all(
            self.coordinator.device.state.features.supports(feature)
            for feature in getattr(description, "feature_keys", ())
        )


class EdifierControlEntity(EdifierEntity):
    """Base class for entities that require an active BLE connection."""

    @property
    def available(self) -> bool:
        """Return if the BLE connection and underlying feature are available."""
        return (
            self.coordinator.connection_enabled
            and self.coordinator.device.initialized
            and super().available
        )
