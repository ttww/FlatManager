import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatDateTime, statusClass } from "../lib/format";
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

export function CodesPage() {
  const [form, setForm] = useState<AccessCodeForm>(initialForm);
  const [codes, setCodes] = useState<AccessCodeSummary[]>([]);
  const [apartmentTimezone, setApartmentTimezone] = useState("UTC");
  const [timezoneBusy, setTimezoneBusy] = useState(false);
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
      setApartmentTimezone("UTC");
    }
  };

  const onSaveTimezone = async () => {
    const normalizedApartmentId = form.apartment_id.trim();
    const normalizedTimezone = apartmentTimezone.trim();
    if (!normalizedApartmentId) {
      setResult("Enter an apartment ID before saving timezone.");
      return;
    }

    if (!normalizedTimezone) {
      setResult("Timezone cannot be empty.");
      return;
    }

    setResult("");
    setTimezoneBusy(true);
    try {
      const apartment = await api.updateApartmentTimezone(
        getAdminToken(),
        normalizedApartmentId,
        normalizedTimezone,
      );
      setApartmentTimezone(apartment.timezone);
      setResult(`Timezone for ${apartment.apartment_id} saved as ${apartment.timezone}.`);
      await loadCodes();
    } catch (error) {
      setResult(`Timezone update failed. ${error instanceof Error ? error.message : ""}`);
    } finally {
      setTimezoneBusy(false);
    }
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setResult("");
    setBusy(true);

    try {
      const normalizedApartmentId = form.apartment_id.trim();
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
            onChange={(event) => {
              const value = event.target.value;
              setForm((prev) => ({ ...prev, apartment_id: value }));
            }}
            onBlur={(event) => {
              void loadApartmentTimezone(event.target.value);
            }}
            required
          />
        </label>

        <label>
          Apartment Timezone (IANA)
          <div className="row-actions">
            <input
              value={apartmentTimezone}
              onChange={(event) => setApartmentTimezone(event.target.value)}
              placeholder="Europe/Berlin"
              required
            />
            <button
              type="button"
              onClick={() => void onSaveTimezone()}
              disabled={timezoneBusy}
            >
              {timezoneBusy ? "Saving..." : "Save Timezone"}
            </button>
          </div>
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
                <td>{formatDateTime(code.valid_from, code.apartment_timezone)}</td>
                <td>{formatDateTime(code.valid_until, code.apartment_timezone)}</td>
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
