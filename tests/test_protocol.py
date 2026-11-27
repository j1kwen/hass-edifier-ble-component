"""Protocol tests for the Edifier BLE integration."""

from __future__ import annotations

import unittest

from custom_components.edifier_ble.const import model_from_service_uuid
from custom_components.edifier_ble.protocol import (
    EQ_BANDS,
    EQ_BANDS_BY_KEY,
    PacketStreamParser,
    build_advanced_audio_data,
    build_eq_band_data,
    build_mr3_eq_band_data,
    build_packet,
    code_to_gain,
    gain_to_code,
    parse_advanced_audio,
    parse_d8_features,
    parse_eq_bands,
    parse_frame,
    parse_media_info,
    parse_mr3_eq_bands,
)


def device_frame(header: int, command: int, data: bytes) -> bytes:
    """Build a valid device response frame for tests."""
    payload = bytes((header, 0xEC, command)) + len(data).to_bytes(2, "big") + data
    return payload + bytes((sum(payload) & 0xFF,))

N300_FEATURES = bytes.fromhex("0000010401010100000001010A130100002004030430")


class BuildPacketTest(unittest.TestCase):
    """Test command frame construction."""

    def test_documented_query_packets(self) -> None:
        """Reference packets from the README should match."""
        self.assertEqual(build_packet(0x61).hex(" "), "aa ec 61 00 00 f7")
        self.assertEqual(build_packet(0x66).hex(" "), "aa ec 66 00 00 fc")
        self.assertEqual(build_packet(0xD8).hex(" "), "aa ec d8 00 00 6e")

    def test_set_volume_packet(self) -> None:
        """Volume command data should be included before the checksum."""
        self.assertEqual(build_packet(0x67, b"\x10").hex(" "), "aa ec 67 00 01 10 0e")


class FrameParserTest(unittest.TestCase):
    """Test response parsing and stream reassembly."""

    def test_parse_frame(self) -> None:
        """A complete response frame should parse."""
        raw = device_frame(0xBB, 0x66, b"\x10\x0a")
        frame = parse_frame(raw)
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.command, 0x66)
        self.assertEqual(frame.data, b"\x10\x0a")

    def test_invalid_checksum_is_rejected(self) -> None:
        """Invalid checksums must not produce a frame."""
        self.assertIsNone(parse_frame(bytes.fromhex("bb ec 66 00 02 10 0a 00")))

    def test_stream_reassembly(self) -> None:
        """Split and concatenated notifications should both parse."""
        first = device_frame(0xBB, 0xC6, b"\x01\x05\x01")
        second = device_frame(0xBB, 0x86, b"\x02\x01")
        parser = PacketStreamParser()

        self.assertEqual(parser.feed(first[:4]), [])
        frames = parser.feed(first[4:] + second)
        self.assertEqual([frame.command for frame in frames], [0xC6, 0x86])
        self.assertEqual(frames[0].data, b"\x01\x05\x01")
        self.assertEqual(frames[1].data, b"\x02\x01")


class FeatureBitmapTest(unittest.TestCase):
    """Test D8 feature bitmap decoding."""

    def test_n300_feature_bitmap(self) -> None:
        """The documented N300 bitmap should decode to the expected features."""
        features = parse_d8_features(N300_FEATURES)
        for feature in (
            "GetDeviceName",
            "SetDeviceName",
            "GetMacAddress",
            "GetFirmwareVersion",
            "Equalizer",
            "InputSourceSettings",
            "VolumeSettings",
            "MusicInfo",
            "SmartLight",
            "BeepSet",
        ):
            self.assertTrue(features.supports(feature), feature)
        self.assertEqual(features.max_device_name_length, 35)


class EqualizerTest(unittest.TestCase):
    """Test equalizer conversion and parsing."""

    def test_gain_conversion(self) -> None:
        """Gain codes should follow the documented formula."""
        self.assertEqual(gain_to_code(-3.0), 0)
        self.assertEqual(gain_to_code(0.0), 6)
        self.assertEqual(gain_to_code(3.0), 12)
        self.assertEqual(code_to_gain(0), -3.0)
        self.assertEqual(code_to_gain(12), 3.0)

    def test_build_and_parse_equalizer_band(self) -> None:
        """A built band record should parse back to the same gain."""
        band = EQ_BANDS_BY_KEY["eq_1khz"]
        data = bytes((0x03, 0x06)) + build_eq_band_data(band, 1.5)
        self.assertEqual(parse_eq_bands(data), {"eq_1khz": 1.5})

    def test_parse_mr3_variable_band_response(self) -> None:
        """MR3 bands are indexed records with a first-record padding byte."""
        frequencies = (62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
        records = bytearray((0x0C, len(frequencies), 0x00, 0x00))
        for index, frequency in enumerate(frequencies):
            if index:
                records.append(index)
            records.extend(frequency.to_bytes(2, "big"))
            records.append(6)
        records.extend(b"Custom EQ")

        gains, indices = parse_mr3_eq_bands(bytes(records))

        self.assertEqual(len(gains), 9)
        self.assertEqual(gains["eq_125hz"], 0.0)
        self.assertEqual(gains["eq_16khz"], 0.0)
        self.assertEqual(indices["eq_125hz"], 1)
        self.assertEqual(indices["eq_16khz"], 8)

    def test_build_mr3_eq_band_payload(self) -> None:
        """MR3 writes one indexed band without the N300 trailing marker."""
        band = next(band for band in EQ_BANDS if band.frequency == 16000)
        self.assertEqual(
            build_mr3_eq_band_data(8, band, 1.5),
            bytes.fromhex("00 08 3e 80 09"),
        )

    def test_parse_and_build_advanced_audio(self) -> None:
        """Advanced audio values round-trip using the MR3 D5/C4 payload shape."""
        response = bytes.fromhex("01 01 00 23 03 00 00")
        self.assertEqual(parse_advanced_audio(response), (35, 3, 0, False))
        self.assertEqual(
            build_advanced_audio_data(35, 3, 0, False),
            bytes.fromhex("00 02 00 23 03 00 00"),
        )
        self.assertIsNone(parse_advanced_audio(bytes.fromhex("01 01 00 23 04 00 00")))


class MediaInfoTest(unittest.TestCase):
    """Test media notification decoding."""

    def test_media_info(self) -> None:
        """UTF-8 title and artist should be decoded."""
        title = "Song".encode()
        artist = "Artist".encode()
        data = bytes((0x01, len(title), len(artist))) + title + artist
        self.assertEqual(parse_media_info(data), (True, "Song", "Artist"))


class ModelMappingTest(unittest.TestCase):
    """Test service UUID model mapping."""

    def test_n300_uuid(self) -> None:
        """The N300 UUID should map to its product code."""
        model = model_from_service_uuid("00007E00-0000-1000-8000-00805F9B34FB")
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.model, "N300")
        self.assertEqual(model.model_code, "EDF100074")

    def test_mr3_uuid(self) -> None:
        """The MR3 UUID should map to its product code."""
        model = model_from_service_uuid("0000F300-0000-1000-8000-00805F9B34FB")
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.model, "MR3")
        self.assertEqual(model.model_code, "EDF-100081")


if __name__ == "__main__":
    unittest.main()
