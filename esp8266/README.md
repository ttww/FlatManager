# ESP8266 Firmware (PlatformIO)

This module contains the firmware project for ESP-01S using PlatformIO.

## Implemented Scope
- Project structure (`src`, `include`, `test`)
- PlatformIO build target and toolchain settings
- Safe relay GPIO initialization (OFF at boot)
- Wi-Fi reconnect manager
- HTTPS long polling with TLS fingerprint pinning
- Device bearer authentication headers
- Command parsing (`none` and `open`) with expiration checks
- Relay pulse execution with hard local clamp
- Command-result reporting (`done`, `failed`, `expired`, `ignored`)
- Exponential retry backoff and watchdog servicing
- OTA flashing support with hostname and password

## Build and upload
```bash
cd esp8266
pio run
pio run -t upload
pio device monitor
```

## Configuration constants
Set values in `platformio.ini` `build_flags`:
- `FM_WIFI_SSID`
- `FM_WIFI_PASSWORD`
- `FM_API_BASE_URL`
- `FM_DEVICE_TOKEN`
- `FM_TLS_CERT_FINGERPRINT`
- `FM_WAIT_COMMAND_PATH`
- `FM_COMMAND_RESULT_PATH`
- `FM_RELAY_PIN`
- `FM_RELAY_ACTIVE_HIGH`
- `FM_MAX_RELAY_PULSE_MS`
- `FM_WIFI_CONNECT_TIMEOUT_MS`
- `FM_RECONNECT_JITTER_MIN_MS`
- `FM_RECONNECT_JITTER_MAX_MS`
- `FM_OTA_HOSTNAME`
- `FM_OTA_PASSWORD`
- `FM_NTP_SERVER_1`
- `FM_NTP_SERVER_2`
- `FM_NTP_SERVER_3`
- `FM_DEFAULT_POLL_TIMEOUT_MS`
- `FM_DEFAULT_HTTP_TIMEOUT_MS`

## OTA notes
- OTA works over local network when Wi-Fi is connected.
- Keep `FM_OTA_PASSWORD` non-empty in production.
- TLS certificate fingerprint must match backend certificate, otherwise requests are rejected.
