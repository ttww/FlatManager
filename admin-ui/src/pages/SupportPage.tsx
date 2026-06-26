import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { getAdminToken } from "../lib/session";
import type { ApartmentTimezone } from "../types";

export function SupportPage() {
  const [apartmentId, setApartmentId] = useState("");
  const [apartmentIds, setApartmentIds] = useState<string[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api
      .listApartmentTimezones(getAdminToken())
      .then((rows: ApartmentTimezone[]) => setApartmentIds(rows.map((r) => r.apartment_id)))
      .catch(() => setApartmentIds([]));
  }, []);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("");

    try {
      await api.manualOpen(getAdminToken(), apartmentId);
      setMessage("Manual open command submitted.");
      setApartmentId("");
    } catch (error) {
      setMessage(`Manual open failed. ${error instanceof Error ? error.message : ""}`);
    }
  };

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Support & Fallback</h2>
        <p>Use this screen for operational recovery when guest-side access fails.</p>
      </header>

      <form className="device-form" onSubmit={onSubmit}>
        <select
          value={apartmentId}
          onChange={(event) => setApartmentId(event.target.value)}
          required
        >
          <option value="">— select apartment —</option>
          {apartmentIds.map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
        <button type="submit" className="primary-button">
          Trigger Manual Open
        </button>
      </form>

      {message ? <p className="inline-message">{message}</p> : null}

      <ul className="support-list">
        <li>Confirm device online status first.</li>
        <li>Use manual open only for verified support cases.</li>
        <li>Provide fallback instructions (physical key) if device remains offline.</li>
      </ul>
    </section>
  );
}
