# ESP Firmware (PlatformIO)

This module contains the firmware project for ESP32-S2 (LOLIN S2 Mini) using PlatformIO.

## Security warning

ESP8266 targets are intentionally removed from the active build configuration.
Do not deploy ESP8266 for FlatManager in production.

Reason: ESP8266 TLS handling in this project relies on certificate fingerprint pinning,
which is operationally weaker and more error-prone than the ESP32-S2 Root CA validation path.
Use ESP32-S2 only.

## Implemented scope

- Project structure (`src`, `include`, `test`)
- PlatformIO build target and toolchain settings for ESP32-S2
- Safe relay GPIO initialization (OFF at boot)
- Wi-Fi reconnect manager
- HTTPS long polling with Root CA validation
- Device bearer authentication headers
- Command parsing (`none` and `open`) with expiration checks
- Relay pulse execution with hard local clamp
- Command-result reporting (`done`, `failed`, `expired`, `ignored`)
- Exponential retry backoff and watchdog servicing
- OTA flashing support with hostname and password

## Supported PlatformIO environments

- `lolin_s2_mini`: ESP32-S2 LOLIN S2 Mini USB/serial upload
- `lolin_s2_mini_ota`: ESP32-S2 LOLIN S2 Mini OTA upload

## Build and upload

```bash
cd esp
pio run
pio run -e lolin_s2_mini -t upload --upload-port /dev/cu.usbmodem01
pio device monitor -e lolin_s2_mini --port /dev/cu.usbmodem01 --baud 115200
```

## OTA upload

```bash
ESP_OTA_PASSWORD=YOUR_OTA_PASSWORD ESP_HOST_IP=$(ipconfig getifaddr en0) pio run -e lolin_s2_mini_ota -t upload
```

If mDNS does not resolve, override upload host with device IP:

```bash
ESP_OTA_PASSWORD=YOUR_OTA_PASSWORD ESP_HOST_IP=$(ipconfig getifaddr en0) pio run -e lolin_s2_mini_ota -t upload --upload-port 192.168.0.123
```

## Secrets setup

`include/secrets.h` is excluded from git. Create it from the template:

```bash
cp include/secrets.h.example include/secrets.h
```

Fill in at least:

- `FM_DEVICE_NAME`
- `FM_WIFI_SSID_1` / `FM_WIFI_PASSWORD_1`
- `FM_API_BASE_URL`
- `FM_DEVICE_TOKEN`
- `FM_OTA_PASSWORD`

## TLS and CA handling

ESP32-S2 uses `include/root_ca.h` with CA validation (`setCACert`).
Renew the Root CA include before expiry using:

```bash
./scripts/update_root_ca.sh
```

The firmware will warn before CA expiry (`FM_ROOT_CA_WARN_BEFORE_DAYS`).
