# ESP8266 Firmware Requirements (ESP-01S, PlatformIO)

## Scope
This module implements the device-side logic for secure long polling, command execution, relay control, and resilient reconnect behavior.

## Hardware Context
- ESP8266 ESP-01S
- Relay module
- Separate power supply for door opener

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

## Security Requirements
- Device must not accept inbound internet commands.
- Only outbound HTTPS to server is allowed.
- Device token must be long and random.
- Token must never be exposed in guest-facing context.

## Reliability and Operations
- Continue operation after transient failures.
- Maintain low latency for command handling through long polling.
- Provide predictable behavior when commands are expired or malformed.

## Out of Scope for This Module File
- Backend validation/rate-limit business rules.
- Guest/admin UI behavior.
