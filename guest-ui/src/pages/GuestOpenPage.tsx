import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { localeMeta, localeOptions, messages, type Locale } from "../i18n/messages";
import { fetchGuestCommandStatus, GuestApiError, requestDoorOpen } from "../lib/api";
import { trackEvent } from "../lib/tracking";

type UiState =
  | "idle"
  | "loading"
  | "accepted"
  | "waiting"
  | "door-opened"
  | "device-failed"
  | "denied"
  | "network-error"
  | "timeout"
  | "rate-limit";

function detectInitialLocale(): Locale {
  const browserLocale = navigator.language.toLowerCase();
  if (browserLocale.startsWith("de")) return "de";
  if (browserLocale.startsWith("cs")) return "cs";
  if (browserLocale.startsWith("uk")) return "uk";
  if (browserLocale.startsWith("ru")) return "ru";
  if (browserLocale.startsWith("ja")) return "ja";
  if (browserLocale.startsWith("zh")) return "zh";
  if (browserLocale.startsWith("ko")) return "ko";
  if (browserLocale.startsWith("ar")) return "ar";
  if (browserLocale.startsWith("he")) return "he";
  if (browserLocale.startsWith("fr")) return "fr";
  if (browserLocale.startsWith("es")) return "es";
  if (browserLocale.startsWith("pt")) return "pt";
  if (browserLocale.startsWith("pl")) return "pl";
  if (browserLocale.startsWith("hu")) return "hu";
  if (browserLocale.startsWith("eo")) return "eo";
  if (browserLocale.startsWith("hi")) return "hi";
  if (browserLocale.startsWith("el")) return "el";
  return "en";
}

export function GuestOpenPage() {
  const [params] = useSearchParams();
  const [locale, setLocale] = useState<Locale>(detectInitialLocale());
  const prefilledApartmentId = params.get("apartment_id");
  const [apartmentId, setApartmentId] = useState(prefilledApartmentId ?? "");
  const [code, setCode] = useState("");
  const [uiState, setUiState] = useState<UiState>("idle");
  const [commandId, setCommandId] = useState<number | null>(null);
  const [errorText, setErrorText] = useState("");
  const isApartmentLocked = prefilledApartmentId !== null;

  const t = messages[locale];
  const currentLocaleMeta = localeMeta[locale];
  const isOffline = typeof navigator !== "undefined" && !navigator.onLine;

  const stateMessage = useMemo(() => {
    if (uiState === "accepted") return t.accepted;
    if (uiState === "waiting") return t.waiting;
    if (uiState === "door-opened") return t.doorOpened;
    if (uiState === "device-failed") return t.deviceFailed;
    if (uiState === "denied") return t.neutralDenied;
    if (uiState === "network-error") return t.networkError;
    if (uiState === "timeout") return t.timeoutError;
    if (uiState === "rate-limit") return t.rateLimited;
    return "";
  }, [t, uiState]);

  const stateVisual = useMemo(() => {
    if (uiState === "accepted" || uiState === "waiting") {
      return { tone: "progress", icon: "", spinner: true };
    }

    if (uiState === "door-opened") {
      return { tone: "ok", icon: "check", spinner: false };
    }

    if (
      uiState === "device-failed" ||
      uiState === "denied" ||
      uiState === "network-error" ||
      uiState === "timeout" ||
      uiState === "rate-limit"
    ) {
      return { tone: "warn", icon: "warn", spinner: false };
    }

    return { tone: "neutral", icon: "", spinner: false };
  }, [uiState]);

  const followUpMessage = useMemo(() => {
    if (
      uiState === "network-error" ||
      uiState === "timeout" ||
      uiState === "rate-limit" ||
      uiState === "device-failed"
    ) {
      return t.retryHint;
    }

    return "";
  }, [t, uiState]);

  const validate = (): boolean => {
    if (!apartmentId.trim()) {
      setErrorText(t.requiredApartment);
      return false;
    }

    if (!/^\d{4,8}$/.test(code.trim())) {
      setErrorText(t.invalidCode);
      return false;
    }

    return true;
  };

  const isSubmitDisabled = uiState === "loading" || uiState === "accepted" || uiState === "waiting";

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorText("");

    if (!validate()) {
      trackEvent("guest_form_validation_failed", {
        reason: "invalid_input",
        hasApartment: Boolean(apartmentId.trim()),
      });
      return;
    }

    if (isOffline) {
      setUiState("network-error");
      trackEvent("guest_submit_blocked_offline", { apartment_id: apartmentId.trim() });
      return;
    }

    setUiState("loading");
    trackEvent("guest_submit_started", {
      apartment_id: apartmentId.trim(),
      code_length: code.trim().length,
    });

    try {
      const result = await requestDoorOpen({
        apartment_id: apartmentId.trim(),
        code: code.trim(),
      });

      if (result.status === "accepted") {
        setUiState("accepted");
        setCommandId(result.command_id ?? null);
      } else {
        setCommandId(null);
        setUiState("denied");
      }

      trackEvent("guest_submit_finished", {
        apartment_id: apartmentId.trim(),
        status: result.status,
      });
    } catch (error) {
      let reason: UiState = "network-error";
      if (error instanceof GuestApiError) {
        if (error.kind === "rate-limit") reason = "rate-limit";
        if (error.kind === "timeout") reason = "timeout";
      }

      setUiState(reason);
      setCommandId(null);
      trackEvent("guest_submit_failed", {
        apartment_id: apartmentId.trim(),
        reason,
      });
    }
  };

  useEffect(() => {
    if ((uiState !== "accepted" && uiState !== "waiting") || commandId === null) {
      return;
    }

    let cancelled = false;
    const apartment = apartmentId.trim();
    const timeoutId = window.setTimeout(() => {
      if (!cancelled) {
        setUiState("device-failed");
        setCommandId(null);
      }
    }, 15000);

    const poll = async () => {
      try {
        const status = await fetchGuestCommandStatus(commandId, apartment);

        if (cancelled) {
          return;
        }

        if (status === "pending") {
          return;
        }

        if (status === "delivered") {
          setUiState("waiting");
          return;
        }

        if (status === "done") {
          setUiState("door-opened");
          setCommandId(null);
          return;
        }

        setUiState("device-failed");
        setCommandId(null);
      } catch {
        if (!cancelled) {
          setUiState("device-failed");
          setCommandId(null);
        }
      }
    };

    void poll();
    const intervalId = window.setInterval(() => {
      void poll();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      window.clearInterval(intervalId);
    };
  }, [apartmentId, commandId, uiState]);

  return (
    <main className="guest-shell" dir={currentLocaleMeta.dir} lang={currentLocaleMeta.lang}>
      <section className="guest-card" aria-live="polite">
        <div className="top-row">
          <div>
            <h1>{t.appTitle}</h1>
            <p className="subtitle">{t.subtitle}</p>
          </div>

          <label className="language-picker" htmlFor="locale">
            <span>{t.language}</span>
            <select id="locale" value={locale} onChange={(event) => setLocale(event.target.value as Locale)}>
              {localeOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <form onSubmit={onSubmit} className="guest-form">
          <label htmlFor="apartment">{t.apartmentLabel}</label>
          {isApartmentLocked ? (
            <div className="apartment-display">{apartmentId}</div>
          ) : (
            <input
              id="apartment"
              value={apartmentId}
              onChange={(event) => setApartmentId(event.target.value)}
              placeholder={t.apartmentPlaceholder}
              autoComplete="off"
              required
            />
          )}

          <label htmlFor="code">{t.codeLabel}</label>
          <input
            id="code"
            inputMode="numeric"
            pattern="[0-9]*"
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D+/g, ""))}
            placeholder={t.codePlaceholder}
            autoComplete="one-time-code"
            required
          />

          {errorText ? <p className="error-text">{errorText}</p> : null}

          <button type="submit" className="cta" disabled={isSubmitDisabled}>
            {uiState === "loading" ? t.submitting : t.submit}
          </button>
        </form>

        {stateMessage ? (
          <div className={`status-panel ${stateVisual.tone} ${uiState}`} role="status" aria-live="polite">
            <span
              className={`status-icon ${stateVisual.spinner ? "is-spinner" : ""}`}
              data-icon={stateVisual.icon}
              aria-hidden="true"
            />
            <p className={`state-message ${uiState}`}>{stateMessage}</p>
          </div>
        ) : null}

        {isOffline ? <p className="hint warning">{t.offlineHint}</p> : null}
        {followUpMessage ? <p className="hint">{followUpMessage}</p> : null}
      </section>
    </main>
  );
}
