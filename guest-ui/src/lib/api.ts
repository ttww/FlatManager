export type GuestOpenPayload = {
  apartment_id: string;
  code: string;
};

export type GuestOpenResult = {
  status: "accepted" | "denied";
  message: string;
};

export class GuestApiError extends Error {
  public readonly kind: "rate-limit" | "timeout" | "network" | "server";

  constructor(kind: "rate-limit" | "timeout" | "network" | "server", message: string) {
    super(message);
    this.kind = kind;
    this.name = "GuestApiError";
  }
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function requestDoorOpen(payload: GuestOpenPayload): Promise<GuestOpenResult> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 8000);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/guest/open`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new GuestApiError("timeout", "Request timed out");
    }
    throw new GuestApiError("network", "Network request failed");
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    if (response.status === 429) {
      throw new GuestApiError("rate-limit", "Too many attempts");
    }
    throw new GuestApiError("server", `Request failed (${response.status})`);
  }

  const body = (await response.json()) as GuestOpenResult;
  if (body.status !== "accepted" && body.status !== "denied") {
    throw new GuestApiError("server", "Unexpected response");
  }

  return body;
}
