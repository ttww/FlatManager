# Guest UI Requirements

## Cross-Module Reference
- Project overview: [../REQUIREMENTS_PROJECT_OVERVIEW.md](../REQUIREMENTS_PROJECT_OVERVIEW.md)

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

## Implementation Checklist

- [ ] Step 1: Define guest UI route structure and deployment path used by QR code.
	Check later: opening the QR target always lands on the intended entry page.
- [ ] Step 2: Define page layout and mobile-first interaction flow.
	Check later: core form is fully usable on common phone viewport sizes.
- [ ] Step 3: Implement secure form model with apartment identifier and numeric code input.
	Check later: only valid numeric format is accepted before submit.
- [ ] Step 4: Integrate submit flow to guest open API endpoint.
	Check later: payload matches API contract and handles network failures.
- [ ] Step 5: Implement loading, success, and denied states with neutral language.
	Check later: denied responses never expose whether code is wrong, expired, or disabled.
- [ ] Step 6: Implement rate-limit and repeated-failure messaging UX.
	Check later: user receives clear next action without technical backend detail.
- [ ] Step 7: Implement resilient behavior for slow responses and temporary offline conditions.
	Check later: timeouts and retry guidance are visible and understandable.
- [ ] Step 8: Apply accessibility checks for contrast, focus order, labels, and tap targets.
	Check later: keyboard navigation and screen-reader labels are complete.
- [ ] Step 9: Add localization-ready copy structure (English-first now).
	Check later: all UI strings are centralized and easy to translate.
- [ ] Step 10: Add tracking hooks for functional events without sensitive data leakage.
	Check later: no raw code or token values appear in logs/analytics.
- [ ] Step 11: Perform end-to-end guest journey validation against API staging.
	Check later: scan, input, submit, and response flow passes on real devices.
