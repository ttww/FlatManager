const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

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

const GUEST_BASE = import.meta.env.VITE_GUEST_BASE_URL || deriveDefaultGuestBase();

export function guestUrl(apartmentId: string): string {
  const base = GUEST_BASE.replace(/\/$/, "");
  return `${base}/guest/?apartment_id=${encodeURIComponent(apartmentId)}`;
}
