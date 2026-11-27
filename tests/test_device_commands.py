"""Device command encoding tests."""

from __future__ import annotations

import unittest
from unittest.mock import create_autospec

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache

from custom_components.edifier_ble.const import (
    MODELS_BY_SERVICE_UUID,
    MR3_SERVICE_UUID,
    TARGET_SERVICE_UUID,
    WRITE_CHARACTERISTIC_UUID,
)
from custom_components.edifier_ble.device import EdifierDevice
from custom_components.edifier_ble.protocol import EdifierFrame, parse_d8_features

N300_FEATURES = bytes.fromhex("0000010401010100000001010A130100002004030430")


class DeviceCommandTest(unittest.IsolatedAsyncioTestCase):
    """Test command payload encoding without a real BLE connection."""

    async def asyncSetUp(self) -> None:
        """Create a device with supported N300 features."""
        self.sent: list[tuple[int, bytes]] = []
        self.device = EdifierDevice(
            "AA:BB:CC:DD:EE:FF",
            MODELS_BY_SERVICE_UUID[TARGET_SERVICE_UUID],
            lambda: None,
        )
        self.device.state.features = parse_d8_features(N300_FEATURES)
        self.device.state.eq_mode = "diy"

        async def _fake_send(command: int, data: bytes = b"", timeout: float = 0):
            self.sent.append((command, data))

        self.device._async_send_command = _fake_send  # type: ignore[method-assign]

    async def test_command_payloads(self) -> None:
        """Each control method should emit the documented protocol payload."""
        await self.device.async_set_source("aux")
        await self.device.async_set_volume(16)
        await self.device.async_set_eq_mode("movie")
        self.device.state.eq_mode = "diy"
        await self.device.async_set_eq_band("eq_1khz", 1.5)
        await self.device.async_set_light("10s", distance="near")
        await self.device.async_set_beep(False)
        await self.device.async_set_device_name("测试音箱")
        await self.device.async_play_control("next")

        self.assertEqual(self.sent[0], (0x62, bytes.fromhex("0F03")))
        self.assertEqual(self.sent[1], (0x67, bytes.fromhex("10")))
        self.assertEqual(self.sent[2], (0xC4, bytes.fromhex("03")))
        self.assertEqual(self.sent[3], (0x44, bytes.fromhex("020003E80907")))
        self.assertEqual(self.sent[4], (0x85, bytes.fromhex("030102")))
        self.assertEqual(self.sent[5], (0x87, bytes.fromhex("020100")))
        self.assertEqual(self.sent[6][0], 0xCA)
        self.assertEqual(self.sent[6][1].decode(), "测试音箱")
        self.assertEqual(self.sent[7], (0xC2, bytes.fromhex("04")))

    async def test_eq_band_requires_diy_mode(self) -> None:
        """Equalizer bands should only be writable in DIY mode."""
        self.device.state.eq_mode = "music"
        with self.assertRaises(ValueError):
            await self.device.async_set_eq_band("eq_1khz", 1.0)

        self.device.state.eq_mode = "diy"
        await self.device.async_set_eq_band("eq_1khz", 1.0)
        self.assertEqual(self.sent[-1][0], 0x44)

    async def test_device_name_byte_limit(self) -> None:
        """The dynamic D8 byte limit should be enforced."""
        with self.assertRaises(ValueError):
            await self.device.async_set_device_name("音" * 12)

    async def test_mute_restores_previous_volume(self) -> None:
        """Mute should remember and restore the previous non-zero volume."""
        await self.device.async_set_volume(11)
        await self.device.async_mute_volume(True)
        await self.device.async_mute_volume(False)
        self.assertEqual(self.sent[-2], (0x67, bytes.fromhex("00")))
        self.assertEqual(self.sent[-1], (0x67, bytes.fromhex("0B")))

    async def test_mr3_volume_uses_device_reported_maximum(self) -> None:
        """The MR3's 30-step range is accepted and encoded as one byte."""
        device = EdifierDevice(
            "AA:BB:CC:DD:EE:FF",
            MODELS_BY_SERVICE_UUID[MR3_SERVICE_UUID],
            lambda: None,
        )
        device._async_send_command = self.device._async_send_command
        device._update_state(EdifierFrame(0xBB, 0x66, bytes.fromhex("1e 14")))
        await device.async_set_volume(30)

        self.assertEqual(device.state.max_volume, 30)
        self.assertEqual(device.state.volume, 30)
        self.assertEqual(self.sent[-1], (0x67, bytes.fromhex("1e")))

    async def test_mr3_advanced_audio_write_preserves_other_values(self) -> None:
        """Changing one advanced value writes the full initialized state."""
        device = EdifierDevice(
            "AA:BB:CC:DD:EE:FF",
            MODELS_BY_SERVICE_UUID[MR3_SERVICE_UUID],
            lambda: None,
        )
        device._async_send_command = self.device._async_send_command
        device.state.features.flags["AdvancedAudio"] = True
        device.state.low_cut_frequency = 35
        device.state.low_cut_slope = 3
        device.state.acoustic_space = 0
        device.state.desktop_mode = False

        await device.async_set_low_cut_frequency(100)

        self.assertEqual(
            self.sent[-1], (0xC4, bytes.fromhex("00 02 00 64 03 00 00"))
        )


class DeviceLoggingTest(unittest.IsolatedAsyncioTestCase):
    """Test transport diagnostics without a real BLE connection."""

    async def asyncSetUp(self) -> None:
        """Create a device with a mocked BLE client."""
        self.device = EdifierDevice(
            "AA:BB:CC:DD:EE:FF",
            MODELS_BY_SERVICE_UUID[TARGET_SERVICE_UUID],
            lambda: None,
        )
        self.client = create_autospec(BleakClientWithServiceCache, instance=True)
        self.client.is_connected = True
        self.device._client = self.client

    async def test_fragmented_response_logs_packets_and_features(self) -> None:
        """Log raw fragments and the assembled D8 frame without losing its response."""
        notification = bytes.fromhex(
            "bb ec d8 00 16 0000010401010100000001010A130100002004030430 18"
        )

        def respond(
            _characteristic: str, _packet: bytes, *, response: bool
        ) -> None:
            self.device._notification_handler(None, bytearray(notification[:4]))
            self.device._notification_handler(None, bytearray(notification[4:]))

        self.client.write_gatt_char.side_effect = respond
        with self.assertLogs("custom_components.edifier_ble.device", "DEBUG") as logs:
            result = await self.device._async_query(0xD8)

        messages = "\n".join(logs.output)
        self.assertIn("AA:BB:CC:DD:EE:FF: TX command=0xD8", messages)
        self.assertIn("packet=aa ec d8 00 00 6e", messages)
        self.assertIn("RX notification (4 bytes): bb ec d8 00", messages)
        self.assertIn("No complete valid frame", messages)
        self.assertNotIn("Ignored malformed notification", messages)
        self.assertIn(
            f"RX frame header=0xBB command=0xD8 data={N300_FEATURES.hex(' ')}",
            messages,
        )
        self.assertIn("D8 supported features:", messages)
        self.assertIn("SmartLight", messages)
        self.assertIn("max device name length: 35 bytes", messages)
        self.assertEqual(result, N300_FEATURES)
        self.assertTrue(self.device.state.features.supports("SmartLight"))
        self.assertEqual(self.device._pending, {})
        self.client.write_gatt_char.assert_awaited_once_with(
            WRITE_CHARACTERISTIC_UUID,
            bytes.fromhex("aa ec d8 00 00 6e"),
            response=False,
        )

    async def test_query_timeout_is_logged_and_propagated(self) -> None:
        """Keep query failures explicit while logging the command and timeout."""
        with self.assertLogs("custom_components.edifier_ble.device", "DEBUG") as logs:
            with self.assertRaisesRegex(
                BleakError, "Timed out waiting for response to command 0xD8"
            ):
                await self.device._async_query(0xD8, timeout=0.01)

        self.assertIn(
            "Response timeout: command=0xD8, timeout=0.01s",
            "\n".join(logs.output),
        )
        self.assertEqual(self.device._pending, {})

    async def test_optional_ack_timeout_remains_nonfatal(self) -> None:
        """Log a missing optional acknowledgement without changing setter behavior."""
        with self.assertLogs("custom_components.edifier_ble.device", "DEBUG") as logs:
            await self.device._async_send_command(0x67, b"\x05", timeout=0.01)

        messages = "\n".join(logs.output)
        self.assertIn("Response timeout: command=0x67, timeout=0.01s", messages)
        self.assertIn("Command 0x67 sent without a response", messages)
        self.assertEqual(self.device._pending, {})

    async def test_write_failure_is_logged_and_propagated(self) -> None:
        """Log the failing command and preserve the original transport error."""
        self.client.write_gatt_char.side_effect = BleakError("write failed")
        with self.assertLogs("custom_components.edifier_ble.device", "DEBUG") as logs:
            with self.assertRaisesRegex(BleakError, "write failed"):
                await self.device._async_query(0xD8)

        self.assertIn("Failed to write command 0xD8", "\n".join(logs.output))
        self.assertEqual(self.device._pending, {})


if __name__ == "__main__":
    unittest.main()
