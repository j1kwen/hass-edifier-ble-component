"""Device command encoding tests."""

from __future__ import annotations

import unittest

from custom_components.edifier_ble.const import (
    MODELS_BY_SERVICE_UUID,
    TARGET_SERVICE_UUID,
)
from custom_components.edifier_ble.device import EdifierDevice
from custom_components.edifier_ble.protocol import parse_d8_features

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


if __name__ == "__main__":
    unittest.main()
