# FlatManager Implementation Execution Plan

## Purpose
This plan defines the recommended implementation order across modules, including mandatory validation gates between phases.

## Source Requirements
- Overview: [REQUIREMENTS_PROJECT_OVERVIEW.md](REQUIREMENTS_PROJECT_OVERVIEW.md)
- API scope: [api/REQUIREMENTS_API.md](api/REQUIREMENTS_API.md)
- ESP8266 scope: [esp8266/REQUIREMENTS_ESP8266.md](esp8266/REQUIREMENTS_ESP8266.md)
- Guest UI scope: [guest-ui/REQUIREMENTS_GUEST_UI.md](guest-ui/REQUIREMENTS_GUEST_UI.md)
- Admin UI scope: [admin-ui/REQUIREMENTS_ADMIN_UI.md](admin-ui/REQUIREMENTS_ADMIN_UI.md)

## Recommended Module Sequence
1. API
2. ESP8266
3. Guest UI
4. Admin UI

## Why This Order
1. API first because all other modules depend on stable contracts and lifecycle rules.
2. ESP8266 second because hardware behavior depends on API command semantics.
3. Guest UI third because it depends on guest endpoint behavior and response contract.
4. Admin UI last because it depends on read and write operations across all backend entities.

## Phase-by-Phase Checklist

### Phase 1: API Foundation and Contracts
- Complete the API checklist in [api/REQUIREMENTS_API.md](api/REQUIREMENTS_API.md).
- Freeze endpoint contracts for:
  - `POST /api/guest/open`
  - `GET /api/device/wait-command`
  - `POST /api/device/command-result`
- Validate data model and command lifecycle behavior.

Gate to proceed:
- Contract tests pass for guest and device endpoints.
- Command expiration and status transitions are verified.
- Rate-limit and neutral error behavior are verified.

### Phase 2: ESP8266 Integration Against API
- Complete the firmware checklist in [esp8266/REQUIREMENTS_ESP8266.md](esp8266/REQUIREMENTS_ESP8266.md).
- Implement long-poll loop and command execution safety rules.
- Implement reporting to command-result endpoint.

Gate to proceed:
- Device can run stable long polling for extended duration.
- Relay never toggles unintentionally at boot.
- Expired commands are rejected and reported.
- Backoff and reconnect behavior are verified under network errors.

### Phase 3: Guest UI Flow
- Complete the guest UI checklist in [guest-ui/REQUIREMENTS_GUEST_UI.md](guest-ui/REQUIREMENTS_GUEST_UI.md).
- Implement QR landing flow, code input, submit, and neutral feedback.
- Validate mobile-first usability and accessibility basics.

Gate to proceed:
- End-to-end guest flow succeeds against API staging.
- Denied and rate-limited states are neutral and clear.
- No sensitive data appears in browser logs or telemetry.

### Phase 4: Admin UI Operations
- Complete the admin UI checklist in [admin-ui/REQUIREMENTS_ADMIN_UI.md](admin-ui/REQUIREMENTS_ADMIN_UI.md).
- Implement code management, status dashboards, command history, and manual open.
- Validate operational workflows and support scenarios.

Gate to complete project implementation:
- Admin auth and access control are verified.
- All critical operations produce audit-visible outcomes.
- Offline and failure scenarios are visible and actionable.

## Cross-Module Validation Matrix

### Validation A: Contract Compatibility
- API request and response schema is consumed correctly by Guest UI and ESP8266.
- Error semantics remain neutral in all public-facing surfaces.

### Validation B: Command Lifecycle Integrity
- Command creation, delivery, execution, and acknowledgment are fully traceable.
- Expired commands cannot trigger a relay action.

### Validation C: Security Baseline
- No plaintext guest codes or device tokens are persisted.
- Device remains outbound-only and non-publicly reachable.
- Rate limits and logging are active for abuse control.

### Validation D: Operational Fallback Readiness
- Manual open path exists and works from admin workflow.
- Guest-facing fallback instructions are present for outage scenarios.
- Device online/offline status is clearly visible from backend-derived signal.

## Agent Execution Rules
1. Implement one checklist step at a time in the active module.
2. Verify each step before moving to the next one.
3. Do not begin the next phase until the current gate is fully satisfied.
4. Record test evidence for every gate decision.
5. If a gate fails, fix within current phase before continuing.
