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

## OTA upload with PlatformIO

When the ESP is already on Wi-Fi, upload the next firmware over the network:

```bash
ESP_OTA_PASSWORD=YOUR_OTA_PASSWORD ESP_HOST_IP=$(ipconfig getifaddr en0) pio run -e esp01_1m_ota -t upload
```

- The default OTA host is `flatmanager-front-door.local`.
- If mDNS is not working, override it with the device IP:
	```bash
	ESP_OTA_PASSWORD=YOUR_OTA_PASSWORD ESP_HOST_IP=$(ipconfig getifaddr en0) pio run -e esp01_1m_ota -t upload --upload-port 192.168.0.123
	```
- The password is not stored in `platformio.ini`; it is taken from `ESP_OTA_PASSWORD`.
- `ESP_HOST_IP` selects the local source interface for OTA packets and avoids intermittent `No route to host` errors on systems with multiple active network interfaces.

## Debug logging

- The build enables ESP8266 core debug output on `Serial` via `build_flags`.
- The first ROM boot message is still printed at `74880` baud by the chip itself, so if you want that line too, open a separate monitor at `74880` immediately after reset.

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
- ESP-01 1M is configured with `eagle.flash.1m64.ld` so OTA has enough room; if layout is changed to larger FS variants, OTA may fail with `OTA error: 1` (begin error).
