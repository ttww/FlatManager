# Guest UI Requirements

## Scope
This module provides the public, mobile-friendly page reached via QR code where guests enter their access code to open the door.

## User Journey
1. Guest scans QR code on site.
2. Browser opens secure HTTPS page.
3. Guest enters access code (preferably 6 digits).
4. UI submits request to backend endpoint.
5. Guest receives clear success/denied feedback.

## Functional Requirements
- Integrate with `POST /api/guest/open`.
- Send `apartment_id` and code.
- Support numeric code input.
- Keep flow simple with minimal steps.
- Provide loading state while request is in progress.

## Security and UX Rules
- Use HTTPS only.
- Keep error messages neutral.
- Do not reveal whether a code is wrong, expired, or disabled.
- Do not expose device token or device internals.
- Handle rate-limit denial gracefully with user-friendly messaging.

## Design Direction
- Modern, clean, and easy to understand for non-technical guests.
- Optimized for phone screens (primary use case).
- Can include tasteful background image styling.
- Accessibility-conscious typography and contrast.
- Fast interaction with clear button/input affordance.

## Content Guidance
- Keep copy short and task-focused.
- Primary action should clearly indicate opening request.
- Failure guidance should remain calm and actionable.

## Edge Cases
- Device offline or delayed response.
- Network interruption from guest phone.
- Repeated input failures/rate limiting.

In these cases, provide a neutral message and clear next step (for example contact host).

## Out of Scope for This Module File
- Admin management workflows.
- Firmware behavior.
- Backend persistence design.
