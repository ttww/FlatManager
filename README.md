# FlatManager

**Secure, QR-based guest access for smart doors**

FlatManager is a complete door access solution for short-term guests. Guests scan a QR code, enter a time-limited access code, and instantly open the door via a secure HTTPS connection to an ESP8266 device.

## Key Features

- 🔐 **Secure**: HTTPS-only, hashed access codes, device tokens, rate limiting, complete audit logs
- 📱 **Guest-Friendly**: QR codes link directly to multilingual code-entry page (17+ languages)
- 🚪 **Reliable**: Long-poll connection ensures device is always reachable; manual override for emergencies
- 📊 **Observable**: Admin dashboard shows real-time device status, command tracking, access logs
- 🏗️ **Simple**: SQLite database, single Docker Compose setup, no external dependencies

## Architecture

```
Guest → QR Code → Web Form (HTTPS)
                 ↓
         Backend API (FastAPI)
         ├─ Validates code
         ├─ Creates command
         └─ Logs access
                 ↓
         ESP8266 Device (Long Poll)
         ├─ Waits for command
         └─ Triggers relay
```

The ESP8266 is **never publicly reachable** — it only initiates outbound HTTPS connections to the server.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Domain with HTTPS (Let's Encrypt recommended)
- ESP8266 with WiFi connectivity

### Build & Run

```bash
# Build and start all services
make prod-upd

# Or manually:
VITE_API_BASE_URL=https://your-domain.com make build upd
```

Services run on:
- Admin UI: `https://your-domain.com/admin/`
- Guest UI: `https://your-domain.com/guest/`
- API: `https://your-domain.com/api/`
- API Docs: `https://your-domain.com/api/docs`

---

## Guest Experience

Guests receive a **personalized QR code link** (pre-filled apartment):

![Guest Entry Form](docs/screenshots/guest-01-open-form.png)

They enter their code, press "Open Door", and see:
- ✅ **Success** → "Door opening requested. Please wait a moment."
- ❌ **Denied** → "Code invalid or not valid."
- ⏱️ **Timeout** → "The request took too long. Please try again."

---

## Admin Dashboard

Admins manage **access codes**, **devices**, and monitor **commands & logs**:

![Admin Access Codes](docs/screenshots/admin-02-codes.png)

Features:
- Create time-limited access codes with optional booking info
- Provision and rotate device tokens
- View real-time device online/offline status
- Track all access attempts and manual opens
- Generate **QR codes** per apartment for sharing

---

## Full Documentation

For detailed setup, configuration, troubleshooting, and deployment guides, see:

📖 **[User Documentation](docs/USER_DOCUMENTATION.md)** — Complete step-by-step guide with screenshots

---

## Project Structure

```
.
├── api/                 # FastAPI backend (Python)
│   ├── src/            # Application code
│   └── migrations/     # Database migrations (Alembic)
├── admin-ui/           # Admin dashboard (React + TypeScript)
├── guest-ui/           # Guest code-entry pages (React + TypeScript)
├── esp8266/            # Device firmware (PlatformIO)
├── docker-compose.yml  # Full stack orchestration
└── docs/               # User documentation & screenshots
```

---

## Security Principles

- ✅ HTTPS end-to-end (no plaintext over network)
- ✅ Access codes hashed with PEPPER + SHA256
- ✅ Device tokens are strong random values
- ✅ ESP device never publicly exposed (outbound only)
- ✅ Rate limiting per IP + per apartment
- ✅ Neutral error messages (no apartment enumeration)
- ✅ Complete access audit logs
- ✅ Short-lived commands (10 seconds default)
- ✅ Bounded relay pulse (server-side + device-side limits)

---

## Deployment

### Local Development
```bash
make up
```

### Production (with HTTPS domain)
```bash
VITE_API_BASE_URL=https://your-domain.com make build upd
```

Requires:
1. Nginx vhost configured (see `docs/USER_DOCUMENTATION.md`)
2. Let's Encrypt certificates in place
3. `.env` file with secrets (not committed to git)

### Clean Docker Build
```bash
./build-clean.sh
```
Removes old images and build cache to ensure no secrets are baked in.

---

## Configuration

Key environment variables (`api/.env`):

```env
ADMIN_TOKEN=your-secure-token
SECURITY_PEPPER=random-32-char-string
DOCS_URL=/api/docs
DEFAULT_OPEN_DURATION_MS=1500
LOCKOUT_FAILED_ATTEMPTS_THRESHOLD=5
```

See `api/.env.example` for all options.

---

## Device Setup (ESP8266)

Configure `esp8266/include/secrets.h`:

```cpp
#define FM_DEVICE_NAME "front-door"
#define FM_WIFI_SSID "YourNetwork"
#define FM_WIFI_PASSWORD "YourPassword"
#define FM_API_BASE_URL "https://your-domain.com"
#define FM_DEVICE_TOKEN "token-from-admin-ui"
#define FM_RELAY_PIN 0  // GPIO for relay module
```

Then build and upload via PlatformIO:

```bash
cd esp8266
pio run -t upload
```

---

## Support & Contributing

- For issues or feature requests, open an issue or PR
- For operational support, see the troubleshooting section in [User Documentation](docs/USER_DOCUMENTATION.md)

---

## License

[Specify your license here, e.g., MIT, GPL, etc.]

---

**Made for secure, frictionless guest access.** Questions? Check the [full documentation](docs/USER_DOCUMENTATION.md).
