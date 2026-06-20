# API Requirements (FastAPI)

## Scope
This module provides all backend endpoints, business rules, command lifecycle management, storage, and security enforcement.

## Recommended Stack
- Python
- FastAPI
- SQLite (initially sufficient for one apartment)
- NGINX as HTTPS reverse proxy

## Core Responsibilities
- Validate guest access requests.
- Authenticate device requests via bearer token.
- Manage short-lived door commands.
- Track device heartbeat (`last_seen`) and optional online state.
- Log all access attempts and command outcomes.
- Expose admin-facing data for status and audit views.

## Endpoint Requirements

### Guest Open Request
`POST /api/guest/open`

Request body:
- `apartment_id`
- `code`

Validation rules:
- Code exists.
- Code is active.
- Current time is within `valid_from` and `valid_until`.
- `used_count < max_uses`.
- Rate limit is not exceeded.
- Apartment/door exists.
- Device is online or command can be briefly buffered.

Response rules:
- Success: accepted/opening message.
- Failure: neutral denied message.
- Never reveal whether the code is wrong, expired, or blocked.

### Device Long Poll
`GET /api/device/wait-command`
Authorization: `Bearer <device_token>`

Behavior:
- Hold request open up to configured timeout (example 60s).
- Return immediately if a valid pending command exists.
- Return `command: none` on timeout.
- Update device `last_seen` each request.

### Device Command Result
`POST /api/device/command-result`
Authorization: `Bearer <device_token>`

Payload includes:
- `command_id`
- `status` (`done`, `failed`, `expired`, `ignored`)
- `message`

Behavior:
- Persist result.
- Update command lifecycle timestamps/status.
- Emit audit log entry.

## Data Model Requirements

### `access_codes`
Fields:
- `id`, `apartment_id`, `code_hash`
- `valid_from`, `valid_until`
- `max_uses`, `used_count`, `active`
- `booking_reference`, optional `guest_name`
- `created_at`, `updated_at`

Rules:
- Never store plaintext code.
- Prefer 6-digit numeric codes.
- 4-digit codes should be avoided or additionally hardened.

### `devices`
Fields:
- `id`, `apartment_id`, `device_name`
- `device_token_hash`
- `last_seen`, `last_ip`, optional `online_status`
- `created_at`, `updated_at`

### `door_commands`
Fields:
- `id`, `device_id`, `apartment_id`
- `command`, `duration_ms`, `status`
- `created_at`, `expires_at`, `delivered_at`, `acknowledged_at`
- `source`, optional `access_code_id`

Rules:
- Commands must be short-lived.
- Default expiration example: `created_at + 10s`.
- Expired commands must never trigger door opening.

Statuses:
- `pending`, `delivered`, `done`, `failed`, `expired`

### `access_log`
Fields:
- `id`, `apartment_id`, optional `access_code_id`
- `timestamp`, `ip_address`, optional `user_agent`
- `result`, optional `reason`, optional `command_id`

Typical results:
- `success`, `denied`, `rate_limited`, `expired`, `device_offline`

## Security and Abuse Protection
- Enforce rate limits per IP and apartment.
- Add temporary lockouts after repeated failed attempts.
- Keep responses neutral to avoid information leakage.
- Protect admin endpoints.
- Keep full audit logging.

## NGINX Requirements for Long Poll
The long-poll endpoint needs specific proxy behavior:
- `proxy_read_timeout` longer than long-poll timeout.
- `proxy_send_timeout` aligned accordingly.
- `proxy_buffering off`.
- HTTPS enabled.
- No unnecessary caching for long-poll path.

## Status Derivation
Device status can be derived from `last_seen`:
- `< 90s` => online
- `>= 90s` => offline/degraded

## Out of Scope for This Module File
- Frontend implementation details.
- Firmware pin-level implementation details.
- NGINX is already setup an us used in a later stage
