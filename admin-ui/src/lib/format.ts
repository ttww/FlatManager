export type TimezoneDisplayMode = "local" | "apartment";

function parseApiDate(input: string): Date {
  // Backend stores UTC; if timezone is omitted in JSON, interpret as UTC.
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(input);
  if (!hasTimezone && /^\d{4}-\d{2}-\d{2}T/.test(input)) {
    return new Date(`${input}Z`);
  }
  return new Date(input);
}

export function formatDateTime(input: string | null, timezone = "UTC"): string {
  if (!input) return "-";
  const date = parseApiDate(input);
  if (Number.isNaN(date.getTime())) return input;

  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "UTC",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  }
}

export function getBrowserTimezone(): string {
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return timezone || "UTC";
  } catch {
    return "UTC";
  }
}

export function getDisplayTimezone(
  mode: TimezoneDisplayMode,
  apartmentTimezone: string,
  browserTimezone: string,
): string {
  return mode === "apartment" ? apartmentTimezone : browserTimezone;
}

export function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (["done", "success", "online", "accepted", "delivered"].includes(normalized)) {
    return "ok";
  }
  if (["pending", "none"].includes(normalized)) {
    return "pending";
  }
  return "warn";
}
