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
- `FM_WIFI_SSID_1`, `FM_WIFI_PASSWORD_1` — primary network (required)
- `FM_WIFI_SSID_2`, `FM_WIFI_PASSWORD_2` — fallback network (optional, leave empty to skip)
- `FM_WIFI_SSID_3`, `FM_WIFI_PASSWORD_3` — fallback network (optional, leave empty to skip)
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

# ESP Firmware (PlatformIO)

This module contains the firmware project for ESP8266 ESP-01S and ESP32-S2 LOLIN S2 Mini using PlatformIO.

## Implemented Scope

- Project structure (`src`, `include`, `test`)
- PlatformIO build targets and toolchain settings for ESP8266 and ESP32-S2
- Safe relay GPIO initialization (OFF at boot)
- Board-specific relay and LED GPIO mapping via build flags
- Wi-Fi reconnect manager
- HTTPS long polling
- ESP8266 TLS validation with certificate fingerprint pinning
- ESP32-S2 TLS validation with generated Root CA include file
- Root CA expiry warning and fail-safe expiry handling
- Device bearer authentication headers
- Command parsing (`none` and `open`) with expiration checks
- Relay pulse execution with hard local clamp
- Command-result reporting (`done`, `failed`, `expired`, `ignored`)
- Exponential retry backoff and watchdog servicing
- OTA flashing support with hostname and password

## Supported PlatformIO environments

- `esp01_1m`: ESP8266 ESP-01S USB/serial upload
- `esp01_1m_ota`: ESP8266 ESP-01S OTA upload
- `lolin_s2_mini`: ESP32-S2 LOLIN S2 Mini USB/serial upload
- `lolin_s2_mini_ota`: ESP32-S2 LOLIN S2 Mini OTA upload

## Secrets setup

`include/secrets.h` is excluded from version control. Create it from the provided example before building:

```bash
cp include/secrets.h.example include/secrets.h
```

Then fill in your values in `secrets.h`:

| Define | Description |
|---|---|
| `FM_DEVICE_NAME` | Hostname used for mDNS and OTA |
| `FM_WIFI_SSID_1` / `FM_WIFI_PASSWORD_1` | Primary Wi-Fi network (required) |
| `FM_WIFI_SSID_2` / `FM_WIFI_PASSWORD_2` | Fallback Wi-Fi network (leave `""` to skip) |
| `FM_WIFI_SSID_3` / `FM_WIFI_PASSWORD_3` | Fallback Wi-Fi network (leave `""` to skip) |
| `FM_API_BASE_URL` | Backend base URL, e.g. `https://your-domain.com` |
| `FM_DEVICE_TOKEN` | Device token from the admin UI |
| `FM_TLS_CERT_FINGERPRINT` | ESP8266 only: SHA-1 fingerprint of the backend certificate |
| `FM_OTA_PASSWORD` | OTA update password (keep non-empty in production) |

Board-specific parameters (relay GPIO, active level, LED pin) stay in `platformio.ini` and do not belong in `secrets.h`.

## Build and upload

Build the default environment:

```bash
cd esp8266
pio run
```

Build a specific board:

```bash
pio run -e esp01_1m
pio run -e lolin_s2_mini
```

Upload ESP8266 over serial:

```bash
pio run -e esp01_1m -t upload
```

Upload ESP32-S2 LOLIN S2 Mini over USB/serial:

```bash
pio run -e lolin_s2_mini -t upload --upload-port /dev/cu.usbmodem01
```

Open serial monitor:

```bash
pio device monitor -e esp01_1m
pio device monitor -e lolin_s2_mini --port /dev/cu.usbmodem01 --baud 115200
```

## OTA upload with PlatformIO

When the device is already on Wi-Fi, upload the next firmware over the local network.

ESP8266:

```bash
ESP_OTA_PASSWORD=YOUR_OTA_PASSWORD ESP_HOST_IP=$(ipconfig getifaddr en0) pio run -e esp01_1m_ota -t upload
```

ESP32-S2:

```bash
ESP_OTA_PASSWORD=YOUR_OTA_PASSWORD ESP_HOST_IP=$(ipconfig getifaddr en0) pio run -e lolin_s2_mini_ota -t upload
```

- The default OTA host is `flatmanager-front-door.local`.
- If mDNS is not working, override it with the device IP:
	```bash
	ESP_OTA_PASSWORD=YOUR_OTA_PASSWORD ESP_HOST_IP=$(ipconfig getifaddr en0) pio run -e esp01_1m_ota -t upload --upload-port 192.168.0.123
	```
- The password is not stored in `platformio.ini`; it is taken from `ESP_OTA_PASSWORD` by `extra_script.py`.
- `ESP_HOST_IP` selects the local source interface for OTA packets and avoids intermittent `No route to host` errors on systems with multiple active network interfaces.
- OTA is local-network based and should remain available even if backend HTTPS validation fails because the Root CA expired.

## Board-specific GPIO mapping

GPIOs are configured through PlatformIO build flags.

Default ESP8266 ESP-01S mapping:

```ini
-D FM_RELAY_PIN=2
-D FM_RELAY_ACTIVE_HIGH=0
-D FM_LED_PIN=2
```

Default ESP32-S2 LOLIN S2 Mini mapping:

```ini
-D FM_RELAY_PIN=16
-D FM_RELAY_ACTIVE_HIGH=0
-D FM_LED_PIN=15
```

Notes:

- ESP32-S2 relay output uses GPIO16.
- ESP32-S2 onboard LED uses GPIO15.
- ESP8266 ESP-01S may share GPIO2 for relay and LED, depending on the relay module wiring.

## TLS and certificate handling

### ESP8266

ESP8266 uses certificate fingerprint pinning:

```ini
-D FM_TLS_CERT_FINGERPRINT=...
```

If the configured fingerprint does not match the backend certificate, HTTPS requests are rejected.

### ESP32-S2

ESP32-S2 uses a generated Root CA include file:

```cpp
#include "root_ca.h"
```

The generated file must be located at:

```text
include/root_ca.h
```

It must provide:

```cpp
const time_t kRootCaNotAfterUnix = ...;
const char kRootCaNotAfterIso8601[] = "...";
const char kRootCa[] PROGMEM = R"EOF_CERT(
...
)EOF_CERT";
```

The firmware uses:

```cpp
client->setCACert(kRootCa);
```

`setInsecure()` must not be used during normal production operation.

## Root CA generation and renewal

Use a script to download the Root CA and regenerate `include/root_ca.h`.

Recommended script path:

```text
scripts/update_root_ca.sh
```

The script should:

- download the ISRG Root X1 certificate
- print subject, issuer, and validity dates
- generate `include/root_ca.h`
- include `kRootCa`
- include `kRootCaNotAfterUnix`
- include `kRootCaNotAfterIso8601`
- work on Linux and macOS

Run it before building ESP32-S2 firmware:

```bash
./scripts/update_root_ca.sh
pio run -e lolin_s2_mini
```

## Root CA expiry behavior

The ESP32-S2 firmware checks the Root CA expiry date after NTP time sync.

Configured flags:

```ini
-D FM_ROOT_CA_WARN_BEFORE_DAYS=90
-D FM_ALLOW_INSECURE_TLS_AFTER_CA_EXPIRE=0
```

Behavior:

- before expiry: HTTPS uses `setCACert(kRootCa)`
- within warning window: firmware logs a warning to update `include/root_ca.h`
- after expiry: firmware refuses HTTPS by default
- insecure fallback is only allowed if explicitly enabled with `FM_ALLOW_INSECURE_TLS_AFTER_CA_EXPIRE=1`

Default production behavior must remain:

```ini
-D FM_ALLOW_INSECURE_TLS_AFTER_CA_EXPIRE=0
```

## Debug logging

- The ESP8266 build enables ESP8266 core debug output on `Serial` via `build_flags`.
- The first ESP8266 ROM boot message is still printed at `74880` baud by the chip itself. To see that line, open a separate monitor at `74880` immediately after reset.
- Normal firmware logs use `115200` baud.

## Configuration constants

Set values in `platformio.ini` `build_flags` or board-specific sections:

- `FM_WIFI_SSID_1`, `FM_WIFI_PASSWORD_1` — primary network (required)
- `FM_WIFI_SSID_2`, `FM_WIFI_PASSWORD_2` — fallback network (optional, leave empty to skip)
- `FM_WIFI_SSID_3`, `FM_WIFI_PASSWORD_3` — fallback network (optional, leave empty to skip)
- `FM_API_BASE_URL`
- `FM_DEVICE_TOKEN`
- `FM_TLS_CERT_FINGERPRINT` (ESP8266)
- `FM_WAIT_COMMAND_PATH`
- `FM_COMMAND_RESULT_PATH`
- `FM_RELAY_PIN`
- `FM_RELAY_ACTIVE_HIGH`
- `FM_LED_PIN`
- `FM_MAX_RELAY_PULSE_MS`
- `FM_WIFI_CONNECT_TIMEOUT_MS`
- `FM_RECONNECT_JITTER_MIN_MS`
- `FM_RECONNECT_JITTER_MAX_MS`
- `FM_OTA_PASSWORD`
- `FM_NTP_SERVER_1`
- `FM_NTP_SERVER_2`
- `FM_NTP_SERVER_3`
- `FM_DEFAULT_POLL_TIMEOUT_MS`
- `FM_DEFAULT_HTTP_TIMEOUT_MS`
- `FM_ROOT_CA_WARN_BEFORE_DAYS` (ESP32-S2)
- `FM_ALLOW_INSECURE_TLS_AFTER_CA_EXPIRE` (ESP32-S2)

## OTA notes

- OTA works over the local network when Wi-Fi is connected.
- Keep `FM_OTA_PASSWORD` non-empty in production.
- ESP8266 TLS certificate fingerprint must match the backend certificate, otherwise requests are rejected.
- ESP32-S2 Root CA must validate the backend certificate chain, otherwise requests are rejected.
- ESP-01 1M is configured with `eagle.flash.1m64.ld` so OTA has enough room. If layout is changed to larger FS variants, OTA may fail with `OTA error: 1` (begin error).

# Scratch
```ini
pio run -e lolin_s2_mini  -t upload  --upload-port /dev/cu.usbmodem01
```
```ini
pio device monitor -e lolin_s2_mini --filter direct --port /dev/cu.usbmodem01
```