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

## Upload size limit for apartment background images

If you upload guest background images through a reverse proxy, increase NGINX request body size above the API limit (default 5 MB):

```nginx
server {
    client_max_body_size 6m;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

Without this setting, NGINX may return `413 Request Entity Too Large` before the request reaches FastAPI.

## Why these settings matter

- `proxy_read_timeout` must be higher than API long-poll timeout.
- `proxy_buffering off` avoids delaying command delivery.
- `proxy_send_timeout` prevents premature connection drops.

## Operational checks

- Confirm device receives commands while long polling through NGINX.
- Confirm command delivery latency stays low under expected load.
- Confirm TLS certificates renew before expiration.
- Confirm admin token and security pepper are set from environment, not defaults.
- Confirm `LOGGING_TIMEZONE` is set explicitly (for example `UTC` or `Europe/Berlin`) so runtime and migration logs match operational expectations.
- Confirm API shutdown does not hang on long-poll connections. The container runs uvicorn with `--timeout-graceful-shutdown 2` to avoid waiting on full long-poll timeouts during stop/restart.

## Recommended production hardening

- Use a process manager for the API service.
- Restrict network exposure to required ports only.
- Rotate admin token and pepper on a defined schedule (`openssl rand -hex 32` generates suitable values).
- Collect and monitor access logs and command failure rates.
