# ESP Firmware Requirements (ESP8266 ESP-01S and ESP32-S2 LOLIN S2 Mini, PlatformIO)

## Cross-Module Reference

- Project overview: [../REQUIREMENTS_PROJECT_OVERVIEW.md](../REQUIREMENTS_PROJECT_OVERVIEW.md)

## Scope

This module implements the device-side logic for secure long polling, command execution, relay control, and resilient reconnect behavior.

## Hardware Context

- ESP8266 ESP-01S target
- ESP32-S2 LOLIN S2 Mini target
- Relay module
- Separate power supply for door opener
- Board-specific GPIO mapping configured via PlatformIO build flags

## Supported PlatformIO Targets

- `esp01_1m`: ESP8266 ESP-01S USB/serial flashing target.
- `esp01_1m_ota`: ESP8266 ESP-01S OTA flashing target.
- `lolin_s2_mini`: ESP32-S2 LOLIN S2 Mini USB/serial flashing target.
- `lolin_s2_mini_ota`: ESP32-S2 LOLIN S2 Mini OTA flashing target.

Common firmware behavior must remain shared where possible. Board-specific differences must be isolated through PlatformIO environments, build flags, and small platform abstraction helpers in code.

## Core Responsibilities

- Connect to apartment Wi-Fi.
- Establish outbound HTTPS connection to backend.
- Authenticate using device token.
- Wait for commands via long poll endpoint.
- Trigger relay only for valid non-expired open commands.
- Report execution results to backend.
- Recover automatically from network/TLS failures.

## Communication Contract

### Wait for Command

- Call `GET /api/device/wait-command` with bearer token.
- If response is `command: none`, reconnect immediately.
- If response is `command: open`, validate expiration and duration constraints before acting.

### Report Result

- Call `POST /api/device/command-result` after each command decision/execution.
- Supported statuses: `done`, `failed`, `expired`, `ignored`.

## Runtime Behavior

### Normal Loop

1. Connect Wi-Fi.
2. Start HTTPS long poll.
3. If no command, reconnect immediately (optional small jitter).
4. If `open` command, check `expires_at`.
5. Pulse relay for bounded duration.
6. Report result.
7. Return to long poll.

### Error and Reconnect Strategy

- On expected long-poll timeout: immediate reconnect.
- On network/TLS errors: exponential backoff up to 30s.
- Suggested sequence: `1s`, `2s`, `5s`, `10s`, `30s`.
- Continue retrying indefinitely.

## Relay Safety Requirements

- Relay must not switch unintentionally during boot.
- Safe default relay state is OFF.
- Hard cap relay pulse duration in firmware (example max 3000 ms).
- If server sends a larger duration, firmware must clamp to local max.
- Use watchdog/recovery mechanisms.
- Use proper relay protection for inductive loads (or suitable relay module design).
- Relay GPIO must be board-specific:
	- ESP8266 ESP-01S default relay pin: `FM_RELAY_PIN=2`.
	- ESP32-S2 LOLIN S2 Mini default relay pin: `FM_RELAY_PIN=16`.
- LED GPIO must be board-specific:
	- ESP8266 ESP-01S default LED pin: `FM_LED_PIN=2` if shared/available.
	- ESP32-S2 LOLIN S2 Mini default LED pin: `FM_LED_PIN=15`.

## Security Requirements

- Device must not accept inbound internet commands.
- Only outbound HTTPS to server is allowed.
- Device token must be long and random.
- Token must never be exposed in guest-facing context.
- ESP8266 HTTPS validation uses the configured certificate fingerprint strategy.
- ESP32-S2 HTTPS validation uses a Root CA certificate include file, generated as `include/root_ca.h`.
- ESP32-S2 must not use `setInsecure()` during normal production operation.
- The generated Root CA header must include:
	- PEM certificate string `kRootCa`.
	- Unix expiry timestamp `kRootCaNotAfterUnix`.
	- ISO-8601 expiry string `kRootCaNotAfterIso8601`.
- Firmware must warn before Root CA expiration using `FM_ROOT_CA_WARN_BEFORE_DAYS`.
- Firmware must refuse HTTPS after Root CA expiration unless `FM_ALLOW_INSECURE_TLS_AFTER_CA_EXPIRE=1` is explicitly configured.
- Default behavior must keep `FM_ALLOW_INSECURE_TLS_AFTER_CA_EXPIRE=0`.

## Reliability and Operations

- Continue operation after transient failures.
- Maintain low latency for command handling through long polling.
- Provide predictable behavior when commands are expired or malformed.
- OTA must remain available on the local network where possible, even if backend HTTPS validation fails because the Root CA expired.
- Root CA renewal must be supported by a script that downloads the CA, validates metadata, and regenerates `include/root_ca.h`.

## Out of Scope for This Module File

- Backend validation/rate-limit business rules.
- Guest/admin UI behavior.

## Implementation Checklist

- [x] Step 1: Define firmware project structure, build settings, and environment constants.
 Check later: firmware builds reproducibly for ESP-01S target.
- [x] Step 2: Implement safe GPIO and relay initialization with OFF default on boot.
 Check later: power-on and reboot never trigger unintended relay activation.
- [x] Step 3: Implement Wi-Fi connection manager with reconnect handling.
 Check later: device recovers from Wi-Fi drops without manual intervention.
- [x] Step 4: Implement HTTPS client setup and certificate validation strategy for ESP8266 and ESP32-S2.
 Check later: ESP8266 accepts only the configured fingerprint; ESP32-S2 accepts only the configured Root CA and refuses expired CA by default.
- [x] Step 5: Implement device authentication header flow for long-poll and result endpoints.
 Check later: missing or invalid token requests fail predictably.
- [x] Step 6: Implement long-poll request loop and timeout reconnect behavior.
 Check later: timeout path reconnects immediately with optional jitter.
- [x] Step 7: Implement open-command parsing and expiration validation.
 Check later: expired commands are rejected and reported as expired or ignored.
- [x] Step 8: Implement relay pulse execution with strict local max duration clamp.
 Check later: any duration above max is capped and logged in result message.
- [x] Step 9: Implement command-result reporting for done, failed, expired, and ignored states.
 Check later: each state is emitted with command_id and diagnostic message.
- [x] Step 10: Implement exponential backoff sequence for network/TLS failure cases.
 Check later: retry timing follows 1s, 2s, 5s, 10s, 30s and then remains capped.
- [x] Step 11: Implement watchdog and recovery behavior for stalled loops.
 Check later: simulated hangs trigger recovery without unsafe relay state changes.
- [x] Step 12: Add hardware-in-the-loop verification plan for relay safety and command latency.
 Check later: measured pulse duration and response latency stay within requirements.
- [x] Step 13: Add OTA flashing support and configuration.
 Check later: OTA update is possible on local network with authenticated access.
- [x] Step 14: Add ESP32-S2 LOLIN S2 Mini PlatformIO environment.
 Check later: `pio run -e lolin_s2_mini` builds successfully.
- [x] Step 15: Add board-specific relay and LED build flags.
 Check later: ESP8266 and ESP32-S2 use separate GPIO mappings without duplicated common flags.
- [x] Step 16: Add Root CA generation flow for ESP32-S2 TLS validation.
 Check later: `include/root_ca.h` contains `kRootCa`, `kRootCaNotAfterUnix`, and `kRootCaNotAfterIso8601`.
- [x] Step 17: Add Root CA expiry handling.
 Check later: firmware warns before expiry and refuses HTTPS after expiry unless insecure fallback is explicitly enabled.

## Hardware-in-the-loop Verification Plan

1. Relay boot safety test:
	- Power cycle device 20x and verify relay never toggles unintentionally.
2. Relay pulse clamp test:
	- Send command with `duration_ms` above configured max and verify measured pulse is clamped.
3. Long-poll latency test:
	- Measure time from accepted guest open request to relay trigger; validate median and worst case.
4. Command expiration test:
	- Send already expired command and verify status is reported as `expired` with no relay pulse.
5. TLS trust test:
	- ESP8266: validate connection works with correct certificate fingerprint and fails with invalid fingerprint.
	- ESP32-S2: validate connection works with generated Root CA and fails with invalid or expired Root CA.
6. Reconnect/backoff test:
	- Simulate AP outage and verify retry sequence follows 1s, 2s, 5s, 10s, 30s max.
7. OTA authorization test:
	- Verify OTA requires configured password and update cannot start without it.
8. ESP32-S2 GPIO test:
	- Verify relay output uses GPIO16 and LED output uses GPIO15.
9. Root CA renewal test:
	- Run the Root CA update script on macOS and Linux and verify the generated header is identical except for generation metadata.
10. Root CA expiry behavior test:
	- Simulate an expired `kRootCaNotAfterUnix` value and verify HTTPS is refused while OTA remains reachable on the local network.
