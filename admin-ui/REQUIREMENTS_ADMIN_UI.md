# Admin UI Requirements

## Cross-Module Reference

- Project overview: [../REQUIREMENTS_PROJECT_OVERVIEW.md](../REQUIREMENTS_PROJECT_OVERVIEW.md)

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

## Implementation Checklist

- [x] Step 1: Define admin SPA information architecture and guarded route map.
 Check later: unauthorized users cannot access admin routes.
- [x] Step 2: Implement authentication and session handling for admin access.
 Check later: login, logout, and session expiry behavior are correct.
- [ ] Step 3: Implement access code list view with filters for state and time windows.
 Check later: active, upcoming, and inactive codes can be differentiated quickly.
- [ ] Step 4: Implement create and edit flow for code validity, max uses, and metadata.
 Check later: API validation errors are displayed clearly and safely.
- [ ] Step 5: Implement deactivate and archive or delete actions with confirmation UX.
 Check later: destructive actions are intentional and audit-visible.
- [ ] Step 6: Implement code usage counters and lifecycle indicators in list/detail views.
 Check later: used_count and max_uses are always consistent with backend data.
- [x] Step 7: Implement device status panel using last_seen-derived online or offline state.
 Check later: stale status is highlighted within defined threshold rules.
- [x] Step 8: Implement command history view with statuses and timestamps.
 Check later: pending, delivered, done, failed, and expired states are understandable.
- [x] Step 9: Implement manual door-open action with clear safety confirmation.
 Check later: action result is visible and tracked in command history.
- [ ] Step 10: Implement access and audit log views with useful filters.
 Check later: security-relevant events are searchable by time and apartment.
- [x] Step 11: Add responsive behavior for desktop and mobile admin scenarios.
 Check later: primary workflows remain usable on smaller screens.
- [ ] Step 12: Add end-to-end validation for critical support workflows.
 Check later: create code, guest use, status update, and fallback manual open all pass.

## Current Implementation Notes

- The SPA currently includes guarded routes, local token session handling, responsive layout, and live views for devices, commands, and logs.
- Device management (create/list/rotate/delete) is wired to backend and functional with existing API endpoints.
- Access-code create UI is implemented and wired, but full list/edit/deactivate/delete depends on backend access-code admin endpoints.
- Manual open action UI is implemented and wired, but depends on a backend manual-open endpoint.
