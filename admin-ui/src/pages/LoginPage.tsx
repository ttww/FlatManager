import type { FormEvent } from "react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { setAdminToken } from "../lib/session";

export function LoginPage() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const location = useLocation();

  const target = (location.state as { from?: string } | null)?.from ?? "/codes";

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!token.trim()) {
      setError("Admin token is required.");
      return;
    }

    setAdminToken(token.trim());
    navigate(target, { replace: true });
  };

  return (
    <main className="login-shell">
      <section className="login-card">
        <p className="eyebrow">Restricted Area</p>
        <h2>Sign in to Admin UI</h2>
        <p className="muted">Use your X-Admin-Token from backend environment configuration.</p>

        <form onSubmit={onSubmit} className="stack">
          <label htmlFor="token">Admin Token</label>
          <input
            id="token"
            type="password"
            value={token}
            onChange={(event) => {
              setToken(event.target.value);
              setError("");
            }}
            placeholder="Paste admin token"
            autoComplete="off"
          />

          {error ? <p className="error-text">{error}</p> : null}

          <button type="submit" className="primary-button">
            Continue
          </button>
        </form>
      </section>
    </main>
  );
}
