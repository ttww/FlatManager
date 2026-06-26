function resolveApiBase(): string {
  const configured = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  const origin = window.location.origin;
  const isRemoteHost = !/^localhost$|^127\.0\.0\.1$/.test(window.location.hostname);

  if (!configured) {
    return origin;
  }

  if ((configured.includes("localhost") || configured.includes("127.0.0.1")) && isRemoteHost) {
    return origin;
  }

  return configured;
}

const API_BASE = resolveApiBase();

function deriveDefaultGuestBase(): string {
  const normalized = API_BASE.replace(/\/$/, "");

  if (normalized.endsWith("/api")) {
    return normalized.slice(0, -4);
  }

  // Local docker-compose serves guest UI separately on 8081.
  if (normalized === "http://localhost:8000" || normalized === "http://127.0.0.1:8000") {
    return normalized.replace(/:8000$/, ":8081");
  }

  return normalized;
}

function resolveGuestBase(): string {
  const configured = (import.meta.env.VITE_GUEST_BASE_URL as string | undefined)?.trim();
  const isRemoteHost = !/^localhost$|^127\.0\.0\.1$/.test(window.location.hostname);

  if (configured && !(configured.includes("localhost") || configured.includes("127.0.0.1"))) {
    return configured;
  }

  if (configured && !isRemoteHost) {
    return configured;
  }

  return deriveDefaultGuestBase();
}

const GUEST_BASE = resolveGuestBase();

export function guestUrl(apartmentId: string): string {
  const base = GUEST_BASE.replace(/\/$/, "");
  return `${base}/guest/?apartment_id=${encodeURIComponent(apartmentId)}`;
}
