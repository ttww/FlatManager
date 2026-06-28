export type GuestOpenPayload = {
  apartment_id: string;
  code: string;
};

export type GuestOpenResult = {
  status: "accepted" | "denied";
  message: string;
  command_id?: number | null;
};

export type GuestCommandStatus = "pending" | "delivered" | "done" | "failed" | "expired";

export class GuestApiError extends Error {
  public readonly kind: "rate-limit" | "timeout" | "network" | "server";

  constructor(kind: "rate-limit" | "timeout" | "network" | "server", message: string) {
    super(message);
    this.kind = kind;
    this.name = "GuestApiError";
  }
}

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

export async function fetchGuestCommandStatus(commandId: number, apartmentId: string): Promise<GuestCommandStatus> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 8000);

  let response: Response;
  try {
    const url = new URL(`${API_BASE}/api/guest/command-status/${commandId}`);
    url.searchParams.set("apartment_id", apartmentId);

    response = await fetch(url.toString(), {
      method: "GET",
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

  const body = (await response.json()) as { status: string };
  if (!body || !["pending", "delivered", "done", "failed", "expired"].includes(body.status)) {
    throw new GuestApiError("server", "Unexpected response");
  }

  return body.status as GuestCommandStatus;
}

export async function fetchGuestBackgroundUrl(apartmentId: string): Promise<string | null> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 8000);

  let response: Response;
  try {
    const url = new URL(`${API_BASE}/api/guest/background-url`);
    url.searchParams.set("apartment_id", apartmentId);
    response = await fetch(url.toString(), {
      method: "GET",
      signal: controller.signal,
    });
  } catch {
    return null;
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    return null;
  }

  const body = (await response.json()) as { image_url?: string | null };
  return typeof body.image_url === "string" && body.image_url ? body.image_url : null;
}
