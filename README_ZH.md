# Edifier BLE for Home Assistant

[English](README.md) | [简体中文](README_ZH.md)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

仓库地址：https://github.com/j1kwen/hass-edifier-ble-component

通过 Bluetooth LE 控制 Edifier 音箱的 Home Assistant 自定义集成。目前支持 Edifier N300，可使用本机 Bluetooth 适配器或 ESPHome Bluetooth Proxy。

## 功能

- 根据广播 Service UUID 自动发现设备
- 查询设备信息，并通过 `D8` 功能位图识别设备能力
- 控制设备名称、音源、音量、播放、均衡器、灯光和提示音
- 通过 BLE 通知实时更新状态
- 提供 BLE 连接开关，可释放控制通道给 Edifier App
- 提供 BLE 信号强度、连接状态和蓝牙音频 MAC 诊断实体

## 支持的设备

| 型号 | 型号代码 | 广播 Service UUID |
|---|---|---|
| Edifier N300 | EDF100074 | `00007e00-0000-1000-8000-00805f9b34fb` |

新增型号需要在 [const.py](custom_components/edifier_ble/const.py) 中添加型号映射，并按需补充协议处理。

## 环境要求

- Home Assistant 2024.7 或更高版本
- 可用的 Bluetooth 适配器，或 ESPHome Bluetooth Proxy

## 安装

### HACS

1. 在 HACS 中打开“集成”。
2. 添加仓库 `https://github.com/j1kwen/hass-edifier-ble-component`，类型选择“Integration”。
3. 搜索 `Edifier BLE` 并安装。
4. 重启 Home Assistant。

### 手动安装

将 `custom_components/edifier_ble` 复制到 Home Assistant 配置目录：

```text
<config>/custom_components/edifier_ble/
```

然后重启 Home Assistant。

## 添加设备

1. 确保 Edifier 音箱已开机并处于 BLE 广播范围。
2. 打开“设置” -> “设备与服务”。
3. 选择自动发现的设备并确认添加。
4. 也可以在集成页面手动添加 `Edifier BLE`。

如果设备正在连接手机 App，请先断开手机连接或关闭集成中的 BLE 连接开关，再尝试重新连接。

## 实体

集成根据设备 `D8` 功能位图动态创建实体。

| 实体 | 类型 | 说明 |
|---|---|---|
| BLE 连接 | Switch | 控制 Home Assistant 是否保持 BLE 连接 |
| 设备名称 | Text | 读取和设置设备名称 |
| BLE 信号强度 | Sensor | 来自 BLE 广播的 RSSI |
| BLE 连接状态 | Binary sensor | 当前 BLE 连接状态 |
| 蓝牙音频 MAC 地址 | Sensor | 来自 `C8` 的经典蓝牙音频 MAC |
| 音源 | Select | 蓝牙、声卡或 AUX |
| 音量 | Number | 0 到 16，0 为静音 |
| 媒体播放器 | Media player | 播放、暂停、上一曲、下一曲、音量和静音 |
| 均衡器模式 | Select | 音乐、监听、游戏、电影和 DIY |
| 均衡器 6 段 | Number | 62 Hz、250 Hz、1 kHz、4 kHz、8 kHz、16 kHz，范围 -3 到 +3 dB，步长 0.5；仅在 DIY 模式下可调 |
| 亮灯时长 | Select | 5 秒、10 秒、20 秒或常亮 |
| 感应距离 | Select | 远、普通或近 |
| 蓝牙提示音 | Switch | 打开或关闭提示音 |

## 注意事项

- 不支持也不会发送关机命令 `CE` 和未知风险命令 `CF`。
- Edifier N300 的 BLE 控制通道同一时间只允许一个中心设备连接。
- 歌曲信息依赖经典蓝牙 AVRCP，只在蓝牙音源模式下由设备主动上报。
- 固件升级后重新连接设备会重新查询 `D8`，自动适配新增或移除的功能。

## 故障排查

### 无法建立连接

- 确认音箱未连接手机 App。
- 确认设备在 Bluetooth Proxy 或适配器范围内。
- 在集成中关闭 BLE 连接开关，等待约 10 秒后再重新打开。
- 查看 Home Assistant 日志中 `custom_components.edifier_ble` 的报错。

### 设备发现后无法添加

确认广播 Service UUID 与支持列表一致。首次添加时集成需要连接设备并读取 `D8` 功能位图，设备必须处于可连接状态。

### 实体显示不可用

BLE 断开时控制实体会显示为不可用。检查“BLE 连接状态”诊断实体以及 BLE 适配器或 ESPHome Proxy 状态。

## 调试日志

在 Home Assistant `configuration.yaml` 中添加：

```yaml
logger:
  default: info
  logs:
    custom_components.edifier_ble: debug
```

## 开发和测试

运行测试：

```bash
python -m unittest discover -s tests -v
```

测试需要安装 Home Assistant 的 Python 环境。

## 参考与引用

- [edifier-proto](https://github.com/GlitchPunkWTF/edifier-proto)
- [remEDIFIER](https://github.com/TheAirBlow/remEDIFIER)
- [bleak-esphome](https://github.com/Bluetooth-Devices/bleak-esphome)
