export function formatDateTime(input: string | null): string {
  if (!input) return "-";
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) return input;

  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
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
