# API Deployment Notes

## HTTPS and reverse proxy

- Terminate TLS at NGINX.
- Forward traffic to FastAPI service bound to localhost.
- Keep API reachable only through HTTPS in production.

## Long polling endpoint

Recommended NGINX location configuration for the device long-poll endpoint:

```nginx
location /api/device/wait-command {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 65s;
    proxy_send_timeout 65s;
    proxy_buffering off;
}
```

## Why these settings matter

- `proxy_read_timeout` must be higher than API long-poll timeout.
- `proxy_buffering off` avoids delaying command delivery.
- `proxy_send_timeout` prevents premature connection drops.

## Operational checks

- Confirm device receives commands while long polling through NGINX.
- Confirm command delivery latency stays low under expected load.
- Confirm TLS certificates renew before expiration.
- Confirm admin token and security pepper are set from environment, not defaults.

## Recommended production hardening

- Use a process manager for the API service.
- Restrict network exposure to required ports only.
- Rotate admin token and pepper on a defined schedule.
- Collect and monitor access logs and command failure rates.
