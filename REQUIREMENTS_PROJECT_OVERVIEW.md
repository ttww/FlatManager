# FlatManager — Project Overview

## Goal

Build a secure and easy-to-use door access solution for short-term guests.

A guest scans a QR code on-site, opens an HTTPS page, enters a time-limited access code, and requests a door open action. The backend validates the request and sends a short-lived command to an ESP8266 device, which triggers a relay for a short pulse.

## High-Level Architecture

```text
Guest
  -> QR code
Guest Web Page (HTTPS)
  -> code input
Backend API validates code
  -> creates door command
ESP8266 keeps HTTPS long-poll connection to server
  -> receives command
Relay triggers door opener briefly
```

Critical principle: the ESP8266 is never publicly reachable. It only creates outbound HTTPS connections to the server.

## Communication Model

Preferred model: HTTPS long polling.

Flow:

1. Device calls `GET /api/device/wait-command`.
2. Server keeps request open (long poll).
3. If no command exists, server returns timeout response (`command: none`).
4. Device reconnects immediately.
5. Guest submits valid code to `POST /api/guest/open`.
6. Server answers open long poll with `command: open`.
7. Device triggers relay for a bounded duration.
8. Device posts result to `POST /api/device/command-result`.

## Shared Security Rules

- Use HTTPS end-to-end.
- Do not expose ESP device to the internet.
- Keep guest access codes and device tokens strictly separate.
- Store access codes hashed (not plaintext).
- Use strong random device tokens.
- Enforce rate limiting (per IP and per apartment).
- Keep error messages neutral.
- Keep complete access logs.
- Use short-lived commands with strict expiration.
- Limit relay pulse server-side and device-side.

## Module Split

- `api/`: FastAPI backend, data model, validation, command queueing, logging.
- `esp8266/`: PlatformIO firmware for long polling, relay control, and safe failover behavior.
- `guest-ui/`: public code-entry pages reached by QR code.
- `admin-ui/`: SPA for management and observability.

## Non-Functional Priorities

- Reliability: guests must not be blocked without fallback.
- Security: least exposure, strong token and code handling.
- Operability: clear device online/offline status and command tracking.
- Simplicity: SQLite-first setup for single apartment, extensible later.

## Required Operational Fallback

A fallback access path is mandatory (physical key or equivalent manual process). The system must never leave guests without an alternative if Wi-Fi/server/device fails.
