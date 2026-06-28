# FlatManager Admin UI

Admin SPA for code management, device operations, command history, and audit visibility.

## Stack

- React
- TypeScript
- Vite
- React Router

## Setup

```bash
cd admin-ui
npm install
```

Optional environment variable:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Optional release version override:

```bash
VITE_APP_VERSION=1.2.3
```

If omitted, the app defaults to `http://127.0.0.1:8000`.
If `VITE_APP_VERSION` is not set, the UI version label uses `package.json` version.

## Run

```bash
npm run dev
```

## Build

```bash
npm run build
```

## Auth model

- Login page stores `X-Admin-Token` in localStorage.
- Protected routes redirect to `/login` when token is missing.
- Logout clears local session token.

## Timezone display

- Admin timestamp tables default to browser-local timezone.
- A global toggle in the admin shell switches between `Local` and `Apartment` timezone display.
- Toggle preference is stored in localStorage.

## Implemented routes

- `/login`
- `/codes`
- `/devices`
- `/commands`
- `/logs`
- `/support`

## Backend endpoint usage

Currently implemented backend endpoints used directly:

- `GET /api/admin/devices`
- `POST /api/admin/devices`
- `POST /api/admin/devices/{id}/rotate-token`
- `DELETE /api/admin/devices/{id}`
- `GET /api/admin/devices/status`
- `GET /api/admin/commands/recent`
- `GET /api/admin/access-logs/recent`

Prepared in UI but dependent on backend endpoint availability:

- `POST /api/admin/access-codes`
- `PATCH /api/admin/access-codes/{id}`
- `POST /api/admin/access-codes/{id}/deactivate`
- `DELETE /api/admin/access-codes/{id}`
- `POST /api/admin/commands/manual-open`
