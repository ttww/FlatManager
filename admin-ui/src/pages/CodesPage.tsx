import { useState } from "react";
import type { FormEvent } from "react";

import { api } from "../lib/api";
import { getAdminToken } from "../lib/session";
import type { AccessCodeForm } from "../types";

const initialForm: AccessCodeForm = {
  apartment_id: "",
  code: "",
  valid_from: "",
  valid_until: "",
  max_uses: 20,
  booking_reference: "",
  guest_name: "",
};

export function CodesPage() {
  const [form, setForm] = useState<AccessCodeForm>(initialForm);
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setResult("");
    setBusy(true);

    try {
      await api.createAccessCode(getAdminToken(), form);
      setResult("Access code created successfully.");
      setForm(initialForm);
    } catch (error) {
      setResult(
        `Create failed. Backend endpoint may not be available yet. ${
          error instanceof Error ? error.message : ""
        }`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Access Codes</h2>
        <p>Create and manage booking-linked codes with validity windows and usage limits.</p>
      </header>

      <form className="grid-form" onSubmit={onSubmit}>
        <label>
          Apartment ID
          <input
            value={form.apartment_id}
            onChange={(event) => setForm((prev) => ({ ...prev, apartment_id: event.target.value }))}
            required
          />
        </label>

        <label>
          Numeric Code
          <input
            value={form.code}
            onChange={(event) => setForm((prev) => ({ ...prev, code: event.target.value }))}
            inputMode="numeric"
            required
          />
        </label>

        <label>
          Valid From
          <input
            type="datetime-local"
            value={form.valid_from}
            onChange={(event) => setForm((prev) => ({ ...prev, valid_from: event.target.value }))}
            required
          />
        </label>

        <label>
          Valid Until
          <input
            type="datetime-local"
            value={form.valid_until}
            onChange={(event) => setForm((prev) => ({ ...prev, valid_until: event.target.value }))}
            required
          />
        </label>

        <label>
          Max Uses
          <input
            type="number"
            min={1}
            max={1000}
            value={form.max_uses}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, max_uses: Number.parseInt(event.target.value, 10) || 1 }))
            }
            required
          />
        </label>

        <label>
          Booking Reference
          <input
            value={form.booking_reference ?? ""}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, booking_reference: event.target.value }))
            }
          />
        </label>

        <label>
          Guest Name
          <input
            value={form.guest_name ?? ""}
            onChange={(event) => setForm((prev) => ({ ...prev, guest_name: event.target.value }))}
          />
        </label>

        <div className="form-actions">
          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? "Creating..." : "Create Code"}
          </button>
        </div>
      </form>

      {result ? <p className="inline-message">{result}</p> : null}

      <p className="muted tiny">
        Additional code list, edit, deactivate, and delete controls are wired for backend endpoints and will
        activate once those endpoints are present.
      </p>
    </section>
  );
}
