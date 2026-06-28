import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatDateTime, getDisplayTimezone, statusClass, type TimezoneDisplayMode } from "../lib/format";
import { getAdminToken } from "../lib/session";
import type { AccessCodeForm, AccessCodeSummary } from "../types";

const initialForm: AccessCodeForm = {
  apartment_id: "",
  code: "",
  valid_from: "",
  valid_until: "",
  max_uses: 20,
  booking_reference: "",
  guest_name: "",
};

type CodesPageProps = {
  timezoneDisplayMode: TimezoneDisplayMode;
  browserTimezone: string;
};

export function CodesPage({ timezoneDisplayMode, browserTimezone }: CodesPageProps) {
  const [form, setForm] = useState<AccessCodeForm>(initialForm);
  const [codes, setCodes] = useState<AccessCodeSummary[]>([]);
  const [apartmentIds, setApartmentIds] = useState<string[]>([]);
  const [apartmentTimezone, setApartmentTimezone] = useState("UTC");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);

  const loadCodes = async () => {
    try {
      const rows = await api.listAccessCodes(getAdminToken());
      setCodes(rows);
    } catch (error) {
      setResult(error instanceof Error ? error.message : "Failed to load access codes.");
    }
  };

  useEffect(() => {
    void loadCodes();
    void (async () => {
      try {
        const apartments = await api.listApartmentTimezones(getAdminToken());
        setApartmentIds(apartments.map((row) => row.apartment_id));
      } catch {
        setApartmentIds([]);
      }
    })();
  }, []);

  const loadApartmentTimezone = async (apartmentId: string) => {
    const normalizedApartmentId = apartmentId.trim();
    if (!normalizedApartmentId) {
      setApartmentTimezone("UTC");
      return;
    }

    try {
      const apartment = await api.getApartmentTimezone(getAdminToken(), normalizedApartmentId);
      setApartmentTimezone(apartment.timezone);
    } catch {
      setApartmentTimezone("Apartment not found");
    }
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setResult("");
    setBusy(true);

    try {
      const normalizedApartmentId = form.apartment_id.trim();
      if (apartmentTimezone === "Apartment not found") {
        setResult("Apartment not found. Create it on the Apartments page first.");
        return;
      }
      const normalizedTimezone = apartmentTimezone.trim() || "UTC";
      const payload: AccessCodeForm = {
        ...form,
        apartment_id: normalizedApartmentId,
        valid_from: form.valid_from,
        valid_until: form.valid_until,
        input_timezone: normalizedTimezone,
      };

      await api.createAccessCode(getAdminToken(), payload);
      setResult("Access code created successfully.");
      setForm(initialForm);
      setApartmentTimezone("UTC");
      await loadCodes();
    } catch (error) {
      setResult(`Create failed. ${error instanceof Error ? error.message : ""}`);
    } finally {
      setBusy(false);
    }
  };

  const onDeactivate = async (codeId: number) => {
    setResult("");
    try {
      await api.deactivateAccessCode(getAdminToken(), codeId);
      await loadCodes();
    } catch (error) {
      setResult(error instanceof Error ? error.message : "Deactivate failed.");
    }
  };

  const onDelete = async (codeId: number) => {
    if (!window.confirm("Delete this access code?")) return;

    setResult("");
    try {
      await api.deleteAccessCode(getAdminToken(), codeId);
      await loadCodes();
    } catch (error) {
      setResult(error instanceof Error ? error.message : "Delete failed.");
    }
  };

  const displayTimezone = (apartmentTimezone: string) =>
    getDisplayTimezone(timezoneDisplayMode, apartmentTimezone, browserTimezone);

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Access Codes</h2>
        <p>Create and manage booking-linked codes with validity windows and usage limits.</p>
      </header>

      <form className="grid-form" onSubmit={onSubmit}>
        <label>
          Apartment
          <select
            value={form.apartment_id}
            onChange={(event) => {
              const value = event.target.value;
              setForm((prev) => ({ ...prev, apartment_id: value }));
              void loadApartmentTimezone(value);
            }}
            required
          >
            <option value="">— select apartment —</option>
            {apartmentIds.map((id) => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>
        </label>

        <label>
          Apartment Timezone
          <input
            value={apartmentTimezone}
            readOnly
            aria-readonly
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

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Apartment</th>
              <th>Status</th>
              <th>Uses</th>
              <th>Valid From</th>
              <th>Valid Until</th>
              <th>Booking</th>
              <th>Guest</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {codes.map((code) => (
              <tr key={code.id}>
                <td>{code.id}</td>
                <td>{code.apartment_id}</td>
                <td>
                  <span className={`status-pill ${statusClass(code.active ? "online" : "failed")}`}>
                    {code.active ? "active" : "inactive"}
                  </span>
                </td>
                <td>{code.used_count}/{code.max_uses}</td>
                <td>{formatDateTime(code.valid_from, displayTimezone(code.apartment_timezone))}</td>
                <td>{formatDateTime(code.valid_until, displayTimezone(code.apartment_timezone))}</td>
                <td>{code.booking_reference ?? "-"}</td>
                <td>{code.guest_name ?? "-"}</td>
                <td>
                  <div className="row-actions">
                    <button
                      type="button"
                      onClick={() => void onDeactivate(code.id)}
                      disabled={!code.active}
                    >
                      Deactivate
                    </button>
                    <button
                      type="button"
                      className="danger"
                      onClick={() => void onDelete(code.id)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
