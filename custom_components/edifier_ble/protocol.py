"""Edifier BLE packet encoding and decoding."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from .models import EdifierFeatures

HOST_HEADER = b"\xaa\xec"
DEVICE_HEADERS = (0xBB, 0xCC)
MAX_FRAME_DATA_LENGTH = 1024

SOURCE_TO_OPTION = {
    0x01: "bluetooth",
    0x02: "soundcard",
    0x03: "aux",
}
OPTION_TO_SOURCE = {value: key for key, value in SOURCE_TO_OPTION.items()}

EQ_MODE_TO_OPTION = {
    0x00: "music",
    0x01: "monitor",
    0x02: "game",
    0x03: "movie",
    0x04: "diy",
}
OPTION_TO_EQ_MODE = {value: key for key, value in EQ_MODE_TO_OPTION.items()}

LIGHT_TIME_TO_OPTION = {
    0x00: "5s",
    0x01: "10s",
    0x02: "20s",
    0x03: "on",
}
OPTION_TO_LIGHT_TIME = {value: key for key, value in LIGHT_TIME_TO_OPTION.items()}

DISTANCE_TO_OPTION = {
    0x00: "far",
    0x01: "normal",
    0x02: "near",
}
OPTION_TO_DISTANCE = {value: key for key, value in DISTANCE_TO_OPTION.items()}

PLAY_OPTION_TO_COMMAND = {
    "play": 0x00,
    "pause": 0x01,
    "next": 0x04,
    "previous": 0x05,
}


@dataclass(frozen=True, slots=True)
class EqBand:
    """An Edifier equalizer band."""

    key: str
    index: int
    frequency: int
    frequency_hi: int
    frequency_lo: int
    label: str


EQ_BANDS: tuple[EqBand, ...] = (
    EqBand("eq_62hz", 0x00, 62, 0x00, 0x3E, "62 Hz"),
    EqBand("eq_250hz", 0x01, 250, 0x00, 0xFA, "250 Hz"),
    EqBand("eq_1khz", 0x02, 1000, 0x03, 0xE8, "1 kHz"),
    EqBand("eq_4khz", 0x03, 4000, 0x0F, 0xA0, "4 kHz"),
    EqBand("eq_8khz", 0x04, 8000, 0x1F, 0x40, "8 kHz"),
    EqBand("eq_16khz", 0x05, 16000, 0x3E, 0x80, "16 kHz"),
)
EQ_BANDS_BY_KEY = {band.key: band for band in EQ_BANDS}
EQ_BANDS_BY_INDEX = {band.index: band for band in EQ_BANDS}
EQ_BANDS_BY_FREQUENCY = {band.frequency: band for band in EQ_BANDS}


@dataclass(frozen=True, slots=True)
class EdifierFrame:
    """A parsed Edifier response frame."""

    header: int
    command: int
    data: bytes


def checksum(payload: bytes) -> int:
    """Return the Edifier checksum for a payload."""
    return sum(payload) & 0xFF


def build_packet(command: int, data: bytes = b"") -> bytes:
    """Build a host command packet."""
    if not 0 <= command <= 0xFF:
        raise ValueError(f"Invalid command: {command!r}")
    if len(data) > 0xFFFF:
        raise ValueError("Command data is too long")
    payload = (
        HOST_HEADER
        + bytes((command,))
        + struct.pack(">H", len(data))
        + data
    )
    return payload + bytes((checksum(payload),))


def parse_frame(raw: bytes) -> EdifierFrame | None:
    """Parse one complete response frame."""
    if len(raw) < 6 or raw[0] not in DEVICE_HEADERS or raw[1] != 0xEC:
        return None

    length = (raw[3] << 8) | raw[4]
    data_end = 5 + length
    if len(raw) != data_end + 1:
        return None
    if checksum(raw[:data_end]) != raw[data_end]:
        return None

    return EdifierFrame(raw[0], raw[2], raw[5:data_end])


class PacketStreamParser:
    """Incrementally parse Edifier response frames from a BLE notification stream."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[EdifierFrame]:
        """Feed notification data and return all complete valid frames."""
        self._buffer.extend(data)
        frames: list[EdifierFrame] = []

        while True:
            start = self._find_start()
            if start is None:
                self._buffer.clear()
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < 5:
                break

            length = (self._buffer[3] << 8) | self._buffer[4]
            if length > MAX_FRAME_DATA_LENGTH:
                del self._buffer[0]
                continue

            frame_length = 6 + length
            if len(self._buffer) < frame_length:
                break

            raw = bytes(self._buffer[:frame_length])
            del self._buffer[:frame_length]
            if frame := parse_frame(raw):
                frames.append(frame)

        return frames

    def _find_start(self) -> int | None:
        """Find the next response frame start."""
        for index, value in enumerate(self._buffer):
            if value in DEVICE_HEADERS and index + 1 < len(self._buffer):
                if self._buffer[index + 1] == 0xEC:
                    return index
            elif value in DEVICE_HEADERS and index + 1 == len(self._buffer):
                return index
        return None


def parse_d8_features(data: bytes) -> EdifierFeatures:
    """Parse the D8 device feature bitmap."""
    flags: dict[str, bool] = {}
    max_name_length = 248

    def has(index: int) -> bool:
        return index < len(data)

    if has(0):
        flags["ANC"] = (data[0] & 0x0F) != 0
        flags["RightChannel"] = bool(data[0] & 0x20)
        flags["PeerHeadphones"] = bool(data[0] & 0x40)
        flags["TwsHeadphones"] = bool(data[0] & 0x80)

    scalar_features = {
        1: "ShowBattery",
        4: "GetMacAddress",
        5: "GetFirmwareVersion",
        6: "Disconnect",
        7: "RePair",
        8: "NoAudioAutoShutdown",
        9: "ShutdownTimer",
        10: "ManualShutdown",
        11: "ShowManual",
        16: "TapControls",
    }
    for index, feature in scalar_features.items():
        if has(index):
            flags[feature] = data[index] > 0

    if has(2):
        flags["GetDeviceName"] = data[2] > 0
    if has(3):
        flags["SetDeviceName"] = data[3] > 0
        max_name_length = {1: 24, 2: 30, 3: 29, 4: 35}.get(data[3], 248)

    if has(12):
        flags["AndroidRfcommOta"] = bool(data[12] & 0x01)
        flags["AndroidBleOta"] = bool(data[12] & 0x02)
        flags["IosRfcommOta"] = bool(data[12] & 0x04)
        flags["IosBleOta"] = bool(data[12] & 0x08)
        flags["ShareMe"] = bool(data[12] & 0x10)
        flags["TapReset"] = bool(data[12] & 0x20)
        flags["StepCount"] = bool(data[12] & 0x40)
        flags["VoiceSwitch"] = bool(data[12] & 0x80)

    if has(13):
        flags["Equalizer"] = data[13] > 0
    if has(14):
        flags["OnShake"] = bool(data[14] & 0x01)
        flags["OffShake"] = bool(data[14] & 0x02)
        flags["CallShake"] = bool(data[14] & 0x04)
        flags["WxShake"] = bool(data[14] & 0x08)
        flags["Shake"] = bool(data[14] & 0x80)
    if has(17):
        flags["LedSettings"] = bool(data[17] & 0x01)
        flags["BeepSwitchSettings"] = bool(data[17] & 0x02)
        flags["InEarDetectionSettings"] = bool(data[17] & 0x04)
        flags["TapSensitiveSettings"] = bool(data[17] & 0x08)
        flags["BeepVolumeSettings"] = bool(data[17] & 0x10)
        flags["FactoryReset"] = bool(data[17] & 0x20)
        flags["GameMode"] = bool(data[17] & 0x40)
        flags["BoxBattery"] = bool(data[17] & 0x80)
    if has(18):
        flags["WearingFitDetection"] = bool(data[18] & 0x01)
        flags["Lhdc"] = bool(data[18] & 0x02)
        flags["Ldac"] = bool(data[18] & 0x04)
        flags["EarmuffsSwitch"] = bool(data[18] & 0x08)
        flags["WindNoiseSettings"] = bool(data[18] & 0x10)
        flags["DeviceLeakDetection"] = bool(data[18] & 0x20)
        flags["ClearPairingRecord"] = bool(data[18] & 0x40)
        flags["LightColorSettings"] = bool(data[18] & 0x80)
    if has(19):
        flags["InputSourceSettings"] = bool(data[19] & 0x01)
        flags["VolumeSettings"] = bool(data[19] & 0x02)
        flags["DragonSound"] = bool(data[19] & 0x04)
        flags["AmbientLightTimingOffSettings"] = bool(data[19] & 0x08)
        flags["MusicInfo"] = not bool(data[19] & 0x10)
        flags["Pressure"] = bool(data[19] & 0x20)
        flags["Touch"] = bool(data[19] & 0x40)
        flags["AmbientLight"] = bool(data[19] & 0x80)
    if has(20):
        flags["SoundSpace"] = bool(data[20] & 0x01)
        flags["PromptToneSettings"] = bool(data[20] & 0x02)
        flags["HiRes"] = bool(data[20] & 0x04)
        flags["Button"] = bool(data[20] & 0x08)
        flags["HearingProtection"] = bool(data[20] & 0x10)
        flags["TimeCalibration"] = bool(data[20] & 0x20)
        flags["Recovery"] = bool(data[20] & 0x40)
        flags["MultipointConnection"] = bool(data[20] & 0x80)
    if has(21):
        flags["TimeCalibration2"] = bool(data[21] & 0x01)
        flags["FastCharge"] = bool(data[21] & 0x02)
        flags["DenoiseMode"] = bool(data[21] & 0x04)
        flags["Study"] = bool(data[21] & 0x08)
        flags["SmartLight"] = bool(data[21] & 0x10)
        flags["BeepSet"] = bool(data[21] & 0x20)
    if has(22):
        flags["HdAudioCodec"] = bool(data[22] & 0x01)
        flags["Allow192K"] = bool(data[22] & 0x80)
    if has(23):
        flags["SavingMode"] = bool(data[23] & 0x01)
        flags["Microphone"] = bool(data[23] & 0x02)
        flags["LineHiRes"] = bool(data[23] & 0x10)
        flags["LanSwitch"] = bool(data[23] & 0x40)

    return EdifierFeatures(flags=flags, max_device_name_length=max_name_length)


def gain_to_code(gain_db: float) -> int:
    """Convert a dB gain to the device gain code."""
    return max(0, min(12, round(6 + gain_db * 2)))


def code_to_gain(code: int) -> float:
    """Convert a device gain code to dB."""
    return round((code - 6) / 2, 1)


def build_eq_band_data(band: EqBand, gain_db: float) -> bytes:
    """Build the data payload for setting one equalizer band."""
    return bytes(
        (
            band.index,
            0x00,
            band.frequency_hi,
            band.frequency_lo,
            gain_to_code(gain_db),
            0x07,
        )
    )


def parse_eq_bands(data: bytes) -> dict[str, float]:
    """Parse an equalizer band response."""
    if len(data) >= 2 and data[0] == 0x03 and data[1] == 0x06:
        offset = 2
    else:
        offset = 0

    gains: dict[str, float] = {}
    while offset + 6 <= len(data):
        record = data[offset : offset + 6]
        frequency = (record[2] << 8) | record[3]
        if band := EQ_BANDS_BY_FREQUENCY.get(frequency):
            gains[band.key] = code_to_gain(record[4])
        offset += 6
    return gains


def parse_firmware_version(data: bytes) -> str | None:
    """Parse a firmware version response."""
    if len(data) != 3:
        return None
    return ".".join(str(value) for value in data)


def parse_mac_address(data: bytes) -> str | None:
    """Parse a MAC address response."""
    if len(data) != 6:
        return None
    return ":".join(f"{value:02X}" for value in data)


def parse_utf8(data: bytes) -> str | None:
    """Decode a UTF-8 protocol string."""
    if not data:
        return None
    return data.decode("utf-8", errors="replace")


def parse_media_info(data: bytes) -> tuple[bool | None, str | None, str | None]:
    """Parse a media-info notification."""
    if len(data) < 3:
        return None, None, None

    playing = data[0] == 0x01
    title_length = data[1]
    artist_length = data[2]
    title_start = 3
    artist_start = title_start + title_length
    artist_end = artist_start + artist_length
    title = data[title_start:artist_start].decode("utf-8", errors="replace")
    artist = data[artist_start:artist_end].decode("utf-8", errors="replace")
    return playing, title or None, artist or None
