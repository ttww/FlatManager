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

Key timezone settings:
- `LOGGING_TIMEZONE` controls log timestamp timezone (IANA name, default `UTC`).
- Stored API data timestamps remain UTC regardless of logging timezone.

Gallery settings:
- `APARTMENT_GALLERY_DIR` controls where apartment gallery files are stored.
- `APARTMENT_GALLERY_MAX_IMAGES` limits images per apartment (default `20`).

## Run (development)

- Start API with auto-reload:
  uv run flatmanager-api

Example with non-UTC log timestamps:

```bash
LOGGING_TIMEZONE=Europe/Berlin uv run flatmanager-api
```

## Checks

- Run lint:
  uv run ruff check .
- Run tests:
  uv run pytest

## Implemented endpoints

- GET /health
- GET /api/admin/apartments
- GET /api/admin/apartments/{apartment_id}
- POST /api/admin/apartments
- PUT /api/admin/apartments/{apartment_id}/timezone
- PATCH /api/admin/apartments/{apartment_id}
- DELETE /api/admin/apartments/{apartment_id}
- POST /api/admin/apartments/{apartment_id}/guest-background
- DELETE /api/admin/apartments/{apartment_id}/guest-background
- GET /api/admin/apartments/{apartment_id}/images
- POST /api/admin/apartments/{apartment_id}/images
- GET /api/admin/apartments/{apartment_id}/images/{image_id}/file
- PATCH /api/admin/apartments/{apartment_id}/images/reorder
- POST /api/admin/apartments/{apartment_id}/images/{image_id}/set-guest-background
- DELETE /api/admin/apartments/{apartment_id}/images/{image_id}
- POST /api/guest/open
- GET /api/guest/background-url
- GET /api/guest/background/{apartment_id}
- GET /api/guest/command-status/{command_id}
- GET /api/device/wait-command
- POST /api/device/command-result
- POST /api/admin/devices
- GET /api/admin/devices
- POST /api/admin/devices/{device_id}/rotate-token
- PATCH /api/admin/devices/{device_id}
- DELETE /api/admin/devices/{device_id}
- GET /api/admin/devices/status
- GET /api/admin/commands/recent
- DELETE /api/admin/commands
- POST /api/admin/commands/manual-open
- GET /api/admin/access-logs/recent
- DELETE /api/admin/access-logs
- GET /api/admin/access-codes
- POST /api/admin/access-codes
- PATCH /api/admin/access-codes/{code_id}
- POST /api/admin/access-codes/{code_id}/deactivate
- DELETE /api/admin/access-codes/{code_id}

## Apartment metadata and gallery notes

- Apartment resources now support address and geo-location fields:
  - `address_line1`, `address_line2`, `postal_code`, `city`, `country_code`
  - `latitude`, `longitude`
- Guest background can be selected from apartment gallery images.
- Gallery images are validated as JPG/PNG/WEBP and limited by:
  - `GUEST_BACKGROUND_MAX_BYTES`
  - `APARTMENT_GALLERY_MAX_IMAGES`

Example: update apartment metadata

```bash
curl -s -X PATCH "http://127.0.0.1:8000/api/admin/apartments/apartment-01" \
  -H "X-Admin-Token: flatmanager-admin-dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "address_line1": "Main Street 1",
    "postal_code": "10115",
    "city": "Berlin",
    "country_code": "DE",
    "latitude": 52.53,
    "longitude": 13.38
  }'
```

Example: upload apartment gallery image and set it as guest background

```bash
# upload
curl -s -X POST "http://127.0.0.1:8000/api/admin/apartments/apartment-01/images" \
  -H "X-Admin-Token: flatmanager-admin-dev-token" \
  -F "file=@./example.jpg"

# set uploaded image id as guest background
curl -s -X POST "http://127.0.0.1:8000/api/admin/apartments/apartment-01/images/1/set-guest-background" \
  -H "X-Admin-Token: flatmanager-admin-dev-token"
```

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
