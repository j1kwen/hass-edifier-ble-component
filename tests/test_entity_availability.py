"""Entity availability tests."""

from __future__ import annotations

import unittest

from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothEntityKey,
)
from homeassistant.components.number import NumberEntityDescription

from custom_components.edifier_ble.const import (
    MODELS_BY_SERVICE_UUID,
    MR3_SERVICE_UUID,
    TARGET_SERVICE_UUID,
)
from custom_components.edifier_ble.entity import (
    BINARY_SENSOR_DESCRIPTIONS,
    MEDIA_PLAYER_DESCRIPTIONS,
    NUMBER_DESCRIPTIONS,
    SELECT_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
    SWITCH_DESCRIPTIONS,
    build_device_info,
    state_to_bluetooth_data,
)
from custom_components.edifier_ble.media_player import EdifierMediaPlayer
from custom_components.edifier_ble.models import EdifierState
from custom_components.edifier_ble.number import EdifierNumber
from custom_components.edifier_ble.protocol import parse_d8_features
from custom_components.edifier_ble.sensor import EdifierSensor

N300_FEATURES = bytes.fromhex("0000010401010100000001010A130100002004030430")


class EntityAvailabilityTest(unittest.IsolatedAsyncioTestCase):
    """Test control and diagnostic availability rules."""

    def setUp(self) -> None:
        """Create a fake processor with an N300 device."""
        state = EdifierState(features=parse_d8_features(N300_FEATURES))
        async def async_play_control(self, action: str) -> None:
            self.play_actions.append(action)

        device = type(
            "Device",
            (),
            {
                "model": MODELS_BY_SERVICE_UUID[TARGET_SERVICE_UUID],
                "state": state,
                "max_device_name_length": 35,
                "initialized": True,
                "play_actions": [],
                "async_play_control": async_play_control,
            },
        )()
        coordinator = type(
            "Coordinator",
            (),
            {
                "address": "AA:BB:CC:DD:EE:FF",
                "name": "Edifier N300",
                "available": True,
                "connection_enabled": True,
                "device": device,
            },
        )()
        self.device = device
        self.processor = type(
            "Processor",
            (),
            {
                "coordinator": coordinator,
                "last_update_success": True,
                "devices": {},
                "entity_names": {},
                "entity_data": {},
            },
        )()

    def test_controls_unavailable_when_disconnected(self) -> None:
        """Controls should become unavailable when BLE is disconnected."""
        number = EdifierNumber(
            self.processor,
            PassiveBluetoothEntityKey(NUMBER_DESCRIPTIONS[0].key, None),
            NUMBER_DESCRIPTIONS[0],
        )
        sensor = EdifierSensor(
            self.processor,
            PassiveBluetoothEntityKey(SENSOR_DESCRIPTIONS[0].key, None),
            SENSOR_DESCRIPTIONS[0],
        )

        self.assertTrue(number.available)
        self.device.initialized = False
        self.assertFalse(number.available)
        self.assertTrue(sensor.available)

    def test_base_description_does_not_crash(self) -> None:
        """A base HA description without feature_keys must not raise."""
        description = NumberEntityDescription(key="volume")
        number = EdifierNumber(
            self.processor,
            PassiveBluetoothEntityKey("volume", None),
            description,
        )
        self.assertTrue(number.available)

    def test_volume_maximum_uses_device_report(self) -> None:
        """The volume number advertises the range reported by the device."""
        self.device.state.max_volume = 30
        description = NUMBER_DESCRIPTIONS[0]
        number = EdifierNumber(
            self.processor,
            PassiveBluetoothEntityKey(description.key, None),
            description,
        )
        self.assertEqual(number.native_max_value, 30)

    def test_ble_address_is_used_for_connections(self) -> None:
        """Device connections should use the BLE advertisement address."""
        self.device.state.mac_address = "C8:24:78:C0:AF:2C"
        info = build_device_info(
            "C8:24:70:C0:AF:2C", self.device.model, self.device.state
        )
        self.assertEqual(
            info["connections"], {("bluetooth", "C8:24:70:C0:AF:2C")}
        )
        self.assertEqual(
            info["identifiers"],
            {
                ("edifier_ble", "C8:24:70:C0:AF:2C"),
                ("edifier_ble", "C8:24:78:C0:AF:2C"),
            },
        )

    def test_equalizer_bands_only_available_in_diy(self) -> None:
        """Equalizer band entities should be disabled outside DIY mode."""
        description = NUMBER_DESCRIPTIONS[1]
        number = EdifierNumber(
            self.processor,
            PassiveBluetoothEntityKey(description.key, None),
            description,
        )

        self.device.state.eq_mode = "music"
        self.assertFalse(number.available)
        self.device.state.eq_mode = "diy"
        self.assertTrue(number.available)

    async def test_media_play_and_pause_services(self) -> None:
        """HA media services should send play and pause commands."""
        media = EdifierMediaPlayer(
            self.processor,
            PassiveBluetoothEntityKey(MEDIA_PLAYER_DESCRIPTIONS[0].key, None),
            MEDIA_PLAYER_DESCRIPTIONS[0],
        )
        await media.async_media_play()
        await media.async_media_pause()
        self.assertEqual(self.device.play_actions, ["play", "pause"])

    def test_diagnostic_values(self) -> None:
        """RSSI and BLE connectivity should be exposed to diagnostics."""
        state = self.device.state
        state.rssi = -54
        state.connected = True
        model = self.device.model

        sensor_data = state_to_bluetooth_data(
            state, model, "AA:BB:CC:DD:EE:FF", SENSOR_DESCRIPTIONS
        )
        binary_data = state_to_bluetooth_data(
            state, model, "AA:BB:CC:DD:EE:FF", BINARY_SENSOR_DESCRIPTIONS
        )

        self.assertEqual(next(iter(sensor_data.entity_data.values())), -54)
        self.assertIs(next(iter(binary_data.entity_data.values())), True)

    def test_mr3_entities_follow_reported_bands_and_advanced_audio(self) -> None:
        """MR3 exposes only parsed EQ bands and valid advanced controls."""
        state = EdifierState()
        state.features.flags.update({"Equalizer": True, "AdvancedAudio": True})
        state.eq_bands = {"eq_125hz": 0.5, "eq_16khz": -1.0}
        state.eq_band_indices = {"eq_125hz": 1, "eq_16khz": 8}
        state.low_cut_frequency = 35
        state.low_cut_slope = 3
        state.acoustic_space = 0
        state.desktop_mode = False
        model = MODELS_BY_SERVICE_UUID["0000f300-0000-1000-8000-00805f9b34fb"]

        number_data = state_to_bluetooth_data(
            state, model, "AA:BB:CC:DD:EE:FF", NUMBER_DESCRIPTIONS
        )
        select_data = state_to_bluetooth_data(
            state, model, "AA:BB:CC:DD:EE:FF", SELECT_DESCRIPTIONS
        )
        switch_data = state_to_bluetooth_data(
            state, model, "AA:BB:CC:DD:EE:FF", SWITCH_DESCRIPTIONS
        )

        number_keys = {key.key for key in number_data.entity_descriptions}
        self.assertIn("eq_125hz", number_keys)
        self.assertIn("eq_16khz", number_keys)
        self.assertNotIn("eq_62hz", number_keys)
        self.assertIn("low_cut_frequency", number_keys)
        select_keys = {key.key for key in select_data.entity_descriptions}
        self.assertIn("eq_mode", select_keys)
        mode_key = PassiveBluetoothEntityKey("eq_mode", None)
        self.assertEqual(
            select_data.entity_descriptions[mode_key].options,
            ["music", "monitor", "custom"],
        )
        self.assertIn("low_cut_slope", select_keys)
        self.assertIn("acoustic_space", select_keys)
        self.assertIn(
            "desktop_mode",
            {key.key for key in switch_data.entity_descriptions},
        )

    def test_mr3_equalizer_available_only_in_custom(self) -> None:
        """MR3 uses Custom rather than N300's DIY to enable band controls."""
        self.device.model = MODELS_BY_SERVICE_UUID[MR3_SERVICE_UUID]
        description = NUMBER_DESCRIPTIONS[1]
        number = EdifierNumber(
            self.processor,
            PassiveBluetoothEntityKey(description.key, None),
            description,
        )
        for mode in (None, "music", "monitor"):
            with self.subTest(mode=mode):
                self.device.state.eq_mode = mode
                self.assertFalse(number.available)
        self.device.state.eq_mode = "custom"
        self.assertTrue(number.available)


if __name__ == "__main__":
    unittest.main()
