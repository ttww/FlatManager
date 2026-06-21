import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { localeOptions, messages, type Locale } from "../i18n/messages";
import { GuestApiError, requestDoorOpen } from "../lib/api";
import { trackEvent } from "../lib/tracking";

type UiState = "idle" | "loading" | "accepted" | "denied" | "network-error" | "timeout" | "rate-limit";

function detectInitialLocale(): Locale {
  const browserLocale = navigator.language.toLowerCase();
  return browserLocale.startsWith("de") ? "de" : "en";
}

export function GuestOpenPage() {
  const [params] = useSearchParams();
  const [locale, setLocale] = useState<Locale>(detectInitialLocale());
  const [apartmentId, setApartmentId] = useState(params.get("apartment_id") ?? "");
  const [code, setCode] = useState("");
  const [uiState, setUiState] = useState<UiState>("idle");
  const [errorText, setErrorText] = useState("");

  const t = messages[locale];
  const isOffline = typeof navigator !== "undefined" && !navigator.onLine;

  const stateMessage = useMemo(() => {
    if (uiState === "accepted") return t.accepted;
    if (uiState === "denied") return t.neutralDenied;
    if (uiState === "network-error") return t.networkError;
    if (uiState === "timeout") return t.timeoutError;
    if (uiState === "rate-limit") return t.rateLimited;
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
      } else {
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
      trackEvent("guest_submit_failed", {
        apartment_id: apartmentId.trim(),
        reason,
      });
    }
  };

  return (
    <main className="guest-shell">
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
          <input
            id="apartment"
            value={apartmentId}
            onChange={(event) => setApartmentId(event.target.value)}
            placeholder={t.apartmentPlaceholder}
            autoComplete="off"
            required
          />

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

          <button type="submit" className="cta" disabled={uiState === "loading"}>
            {uiState === "loading" ? t.submitting : t.submit}
          </button>
        </form>

        {stateMessage ? <p className={`state-message ${uiState}`}>{stateMessage}</p> : null}

        {isOffline ? <p className="hint warning">{t.offlineHint}</p> : null}
        <p className="hint">{t.retryHint}</p>
        <p className="hint">{t.contactHost}</p>
      </section>
    </main>
  );
}
