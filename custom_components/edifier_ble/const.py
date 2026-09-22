"""Constants for the Edifier BLE integration."""

from __future__ import annotations

from .models import DEFAULT_MAX_DEVICE_NAME_LENGTH, EdifierModel

DOMAIN = "edifier_ble"
NAME = "Edifier BLE"
MANUFACTURER = "Edifier"

CONF_MODEL = "model"
CONF_CONNECTION_ENABLED = "connection_enabled"

TARGET_SERVICE_UUID = "00007e00-0000-1000-8000-00805f9b34fb"
EDIFIER_COMPANY_ID = 0x07E0

GATT_SERVICE_UUID = "48097e01-1a48-11e9-ab14-d663bd873d93"
WRITE_CHARACTERISTIC_UUID = "48090002-1a48-11e9-ab14-d663bd873d93"
NOTIFY_CHARACTERISTIC_UUID = "48090001-1a48-11e9-ab14-d663bd873d93"

MODELS_BY_SERVICE_UUID: dict[str, EdifierModel] = {
    TARGET_SERVICE_UUID: EdifierModel(
        service_uuid=TARGET_SERVICE_UUID,
        model="N300",
        model_code="EDF100074",
        manufacturer=MANUFACTURER,
    ),
}

MODELS_BY_MODEL_CODE: dict[str, EdifierModel] = {
    model.model_code: model for model in MODELS_BY_SERVICE_UUID.values()
}

DEFAULT_CONNECTION_ENABLED = True
REFRESH_INTERVAL_SECONDS = 60
QUERY_TIMEOUT_SECONDS = 3.0
COMMAND_TIMEOUT_SECONDS = 2.0

# Protocol commands. CE/CF are intentionally not represented because they are
# unsafe and must never be exposed by the integration.
CMD_QUERY_EQ_BANDS = 0x43
CMD_SET_EQ_BAND = 0x44
CMD_MEDIA_INFO = 0x50
CMD_QUERY_SOURCE = 0x61
CMD_SET_SOURCE = 0x62
CMD_QUERY_VOLUME = 0x66
CMD_SET_VOLUME = 0x67
CMD_SOURCE_STATUS = 0x68
CMD_QUERY_LIGHT = 0x84
CMD_SET_LIGHT = 0x85
CMD_QUERY_BEEP = 0x86
CMD_SET_BEEP = 0x87
CMD_PLAY_CONTROL = 0xC2
CMD_SET_EQ_MODE = 0xC4
CMD_GET_FIRMWARE = 0xC6
CMD_GET_MAC = 0xC8
CMD_GET_DEVICE_NAME = 0xC9
CMD_SET_DEVICE_NAME = 0xCA
CMD_QUERY_EQ_MODE = 0xD5
CMD_QUERY_FEATURES = 0xD8

# Entity keys.
KEY_CONNECTION = "connection"
KEY_DEVICE_NAME = "device_name"
KEY_AUDIO_MAC_ADDRESS = "audio_mac_address"
KEY_RSSI = "rssi"
KEY_CONNECTION_STATUS = "connection_status"
KEY_SOURCE = "source"
KEY_VOLUME = "volume"
KEY_MEDIA_PLAYER = "media_player"
KEY_EQ_MODE = "eq_mode"
KEY_LIGHT_TIME = "light_time"
KEY_LIGHT_DISTANCE = "light_distance"
KEY_BEEP = "beep"


def model_from_service_uuid(service_uuid: str) -> EdifierModel | None:
    """Return the known model for a Bluetooth service UUID."""
    return MODELS_BY_SERVICE_UUID.get(service_uuid.lower())


def model_from_service_uuids(service_uuids: list[str] | tuple[str, ...]) -> EdifierModel | None:
    """Return the first known model from advertised service UUIDs."""
    for service_uuid in service_uuids:
        if model := model_from_service_uuid(service_uuid):
            return model
    return None


def model_from_model_code(model_code: str | None) -> EdifierModel | None:
    """Return a model by its product code."""
    if not model_code:
        return None
    return MODELS_BY_MODEL_CODE.get(model_code)
