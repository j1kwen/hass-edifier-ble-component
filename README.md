# Edifier BLE for Home Assistant

[English](README.md) | [简体中文](README_ZH.md)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Repository: https://github.com/j1kwen/hass-edifier-ble-component

A Home Assistant custom integration for controlling Edifier speakers over Bluetooth LE. Edifier N300 is currently supported. The integration works with a local Bluetooth adapter or an ESPHome Bluetooth Proxy.

## Features

- Automatic discovery by advertised Service UUID
- Device information and feature detection using the `D8` bitmap
- Controls for device name, input source, volume, playback, equalizer, light, and prompt tone
- Real-time state updates from BLE notifications
- BLE connection switch to release the control channel for the Edifier app
- Diagnostic entities for BLE signal strength, connection state, and Bluetooth audio MAC

## Supported Devices

| Model | Model Code | Advertised Service UUID |
|---|---|---|
| Edifier N300 | EDF100074 | `00007e00-0000-1000-8000-00805f9b34fb` |

To add another model, extend the model mapping in [const.py](custom_components/edifier_ble/const.py) and add any required protocol handling.

## Requirements

- Home Assistant 2024.7 or newer
- A supported Bluetooth adapter or ESPHome Bluetooth Proxy

## Installation

### HACS

1. Open HACS and select “Integrations”.
2. Add `https://github.com/j1kwen/hass-edifier-ble-component` as a custom repository with category “Integration”.
3. Search for `Edifier BLE` and install it.
4. Restart Home Assistant.

### Manual Installation

Copy `custom_components/edifier_ble` into your Home Assistant configuration directory:

```text
<config>/custom_components/edifier_ble/
```

Restart Home Assistant.

## Adding the Device

1. Power on the Edifier speaker and keep it within BLE range.
2. Open “Settings” -> “Devices & services”.
3. Select the discovered device and confirm setup.
4. You can also add `Edifier BLE` manually from the integrations page.

If the speaker is connected to the Edifier mobile app, disconnect the phone or turn off the integration's BLE connection switch before reconnecting.

## Entities

Entities are created dynamically from the device `D8` feature bitmap.

| Entity | Type | Description |
|---|---|---|
| BLE connection | Switch | Controls whether Home Assistant keeps the BLE connection open |
| Device name | Text | Reads and writes the device name |
| BLE signal strength | Sensor | RSSI from BLE advertisements |
| BLE connection status | Binary sensor | Current BLE connection state |
| Bluetooth audio MAC address | Sensor | Classic Bluetooth audio MAC returned by `C8` |
| Input source | Select | Bluetooth, sound card, or AUX |
| Volume | Number | 0 to 16, where 0 is mute |
| Media player | Media player | Play, pause, previous, next, volume, and mute |
| Equalizer preset | Select | Music, monitor, game, movie, and DIY |
| Six equalizer bands | Number | 62 Hz, 250 Hz, 1 kHz, 4 kHz, 8 kHz, 16 kHz; -3 to +3 dB in 0.5 dB steps; adjustable only in DIY mode |
| Light duration | Select | 5 seconds, 10 seconds, 20 seconds, or always on |
| Sensor distance | Select | Far, normal, or near |
| Bluetooth prompt tone | Switch | Enables or disables prompt tones |

## Important Notes

- The shutdown command `CE` and the unknown risk command `CF` are never exposed.
- The Edifier N300 BLE control channel supports only one central connection at a time.
- Media information depends on classic Bluetooth AVRCP and is reported only in Bluetooth source mode.
- Reconnecting after a firmware update performs another `D8` query and adapts to added or removed features.

## Troubleshooting

### Cannot Connect

- Make sure the speaker is not connected to the Edifier mobile app.
- Confirm the device is within range of the adapter or Bluetooth Proxy.
- Turn the integration's BLE connection switch off, wait about 10 seconds, then turn it back on.
- Check Home Assistant logs for `custom_components.edifier_ble` errors.

### Device Discovered but Setup Fails

Confirm that the advertised Service UUID is supported. Initial setup connects to the device and reads the `D8` feature bitmap, so the device must be connectable.

### Entities Are Unavailable

Control entities are unavailable while BLE is disconnected. Check the BLE connection status diagnostic entity and the Bluetooth adapter or ESPHome Proxy.

## Debug Logging

Add this to Home Assistant `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.edifier_ble: debug
```

## Development and Tests

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

The tests require a Python environment with Home Assistant installed.

## References

- [edifier-proto](https://github.com/GlitchPunkWTF/edifier-proto)
- [remEDIFIER](https://github.com/TheAirBlow/remEDIFIER)
- [bleak-esphome](https://github.com/Bluetooth-Devices/bleak-esphome)
