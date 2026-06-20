# FlatManager API

Backend implementation using uv, FastAPI, SQLModel, and Alembic.

## Prerequisites

- Python 3.12+
- uv

## Setup

1. Install dependencies:
   uv sync
2. Copy environment template:
   cp .env.example .env

## Run (development)

- Start API with auto-reload:
  uv run flatmanager-api

## Checks

- Run lint:
  uv run ruff check .
- Run tests:
  uv run pytest

## Implemented endpoints

- GET /health
- POST /api/guest/open
- GET /api/device/wait-command
- POST /api/device/command-result
- POST /api/admin/devices
- GET /api/admin/devices
- POST /api/admin/devices/{device_id}/rotate-token
- DELETE /api/admin/devices/{device_id}
- GET /api/admin/devices/status
- GET /api/admin/commands/recent
- GET /api/admin/access-logs/recent

## Example: Device provisioning flow

Create a new device and receive a one-time raw bearer token:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/admin/devices" \
  -H "X-Admin-Token: flatmanager-admin-dev-token" \
  -H "Content-Type: application/json" \
  -d '{"apartment_id":"apartment-01","device_name":"Front Door ESP"}'
```

Use returned `raw_token` on ESP in the Authorization header:

```bash
curl -s "http://127.0.0.1:8000/api/device/wait-command" \
  -H "Authorization: Bearer <raw_token_from_create_response>"
```

Rotate token if needed (invalidates previous token immediately):

```bash
curl -s -X POST "http://127.0.0.1:8000/api/admin/devices/1/rotate-token" \
  -H "X-Admin-Token: flatmanager-admin-dev-token"
```

## Migrations

- Create migration: uv run alembic revision --autogenerate -m "message"
- Apply migration: uv run alembic upgrade head

## Deployment notes

See [DEPLOYMENT_NOTES.md](DEPLOYMENT_NOTES.md) for NGINX long-poll and HTTPS guidance.

## Next implementation focus

- Replace startup event with FastAPI lifespan hook
- Add stronger admin authentication strategy
- Add persistence-backed rate-limit counters if horizontal scaling is needed
