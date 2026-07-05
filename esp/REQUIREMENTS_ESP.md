# ESP Firmware Requirements (ESP32-S2 LOLIN S2 Mini, PlatformIO)

## Security Warning

ESP8266 is deprecated for FlatManager deployments and must not be used for new installations.

Reason: ESP8266 support in this project depends on certificate fingerprint pinning, which is less robust operationally than the ESP32-S2 Root CA trust model.

## Scope

This module implements device-side logic for secure long polling, command execution, relay control, and reconnect behavior on ESP32-S2.

## Supported PlatformIO Targets

- `lolin_s2_mini`: ESP32-S2 LOLIN S2 Mini USB/serial flashing target
- `lolin_s2_mini_ota`: ESP32-S2 LOLIN S2 Mini OTA flashing target

## Security Requirements

- Device must initiate outbound HTTPS only.
- Device token must be long and random.
- ESP32-S2 HTTPS validation must use Root CA include file (`include/root_ca.h`).
- ESP32-S2 must not use `setInsecure()` in normal production operation.
- Firmware must warn before Root CA expiration.
- Firmware must refuse HTTPS after Root CA expiration unless explicitly configured otherwise.

## Build/Validation

- Build with `pio run -e lolin_s2_mini`.
- Validate OTA flow with `lolin_s2_mini_ota`.
- Verify relay defaults to OFF at boot and pulse clamp limits are enforced.
