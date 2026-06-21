type TrackPayload = Record<string, string | number | boolean | null | undefined>;

export function trackEvent(event: string, payload: TrackPayload = {}): void {
  const safePayload = { ...payload };

  if ("code" in safePayload) {
    delete safePayload.code;
  }
  if ("token" in safePayload) {
    delete safePayload.token;
  }

  if (typeof window !== "undefined") {
    const win = window as Window & { dataLayer?: unknown[] };
    if (Array.isArray(win.dataLayer)) {
      win.dataLayer.push({ event, ...safePayload });
    }
  }

  if (import.meta.env.DEV) {
    console.info("[track]", event, safePayload);
  }
}
