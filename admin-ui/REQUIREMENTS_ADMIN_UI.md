# Admin UI Requirements

## Scope
This module provides the management interface for hosts/admins to control access codes, observe device state, monitor command outcomes, and handle operational issues.

## Core Features
- Create access code.
- Set validity window (check-in/check-out aligned).
- Deactivate code.
- Delete or archive code.
- View code usage counters.
- View access logs.
- View device status and last seen timestamp.
- Trigger manual door open.
- View door command statuses.

## Recommended Information Views
- Active and upcoming access codes.
- Code lifecycle metadata (`valid_from`, `valid_until`, `max_uses`, `used_count`, active state).
- Device panel with online/offline indication from backend status.
- Recent commands with status transitions.
- Audit trail for guest attempts and admin actions.

## Status Presentation Rules
- Show clear device online/offline state based on backend-provided `last_seen` logic.
- Show last successful door-open event timestamp.
- Highlight stale device connectivity and failed commands.

## Security Requirements
- Admin area must be protected by authentication/authorization.
- Admin actions must be logged.
- Sensitive values (raw guest codes, raw device token) must never be displayed.
- UI should avoid leaking detailed denial reasons to public channels.

## Operational Requirements
- Support manual opening for support/fallback workflows.
- Surface failures quickly (offline device, repeated denied attempts, command failures).
- Keep workflows efficient for mobile and desktop admin use.

## Optional Future Features
- iCal/Airbnb calendar import.
- Automatic code generation from bookings.
- Specialized codes (cleaner, maintenance).
- Notifications on successful door opening.
- Offline alerting.

## Out of Scope for This Module File
- Firmware-level relay timing implementation.
- Backend internal queue/storage implementation details.
- Guest-facing page behavior specifics.
