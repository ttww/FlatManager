import { useEffect, useState } from "react";

import { QrModal } from "../components/QrModal";
import { api } from "../lib/api";
import { getAdminToken } from "../lib/session";
import type { AccessCodeSummary, AdminDevice, ApartmentTimezone } from "../types";

type ApartmentSummary = {
  apartmentId: string;
  timezone: string;
  deviceCount: number;
  codeCount: number;
  activeCodeCount: number;
};

const GUEST_BASE = import.meta.env.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL.replace(/\/api$/, "")
  : window.location.origin;

function guestUrl(apartmentId: string): string {
  const base = GUEST_BASE.replace(/\/$/, "");
  return `${base}/guest/?apartment_id=${encodeURIComponent(apartmentId)}`;
}

function summarizeApartments(
  apartments: ApartmentTimezone[],
  devices: AdminDevice[],
  codes: AccessCodeSummary[],
): ApartmentSummary[] {
  const byApartment = new Map<string, ApartmentSummary>();

  for (const apartment of apartments) {
    byApartment.set(apartment.apartment_id, {
      apartmentId: apartment.apartment_id,
      timezone: apartment.timezone,
      deviceCount: 0,
      codeCount: 0,
      activeCodeCount: 0,
    });
  }

  for (const device of devices) {
    const current = byApartment.get(device.apartment_id) ?? {
      apartmentId: device.apartment_id,
      timezone: device.apartment_timezone || "UTC",
      deviceCount: 0,
      codeCount: 0,
      activeCodeCount: 0,
    };
    current.deviceCount += 1;
    byApartment.set(device.apartment_id, current);
  }

  for (const code of codes) {
    const current = byApartment.get(code.apartment_id) ?? {
      apartmentId: code.apartment_id,
      timezone: code.apartment_timezone || "UTC",
      deviceCount: 0,
      codeCount: 0,
      activeCodeCount: 0,
    };
    current.codeCount += 1;
    if (code.active) {
      current.activeCodeCount += 1;
    }
    byApartment.set(code.apartment_id, current);
  }

  return [...byApartment.values()].sort((left, right) => left.apartmentId.localeCompare(right.apartmentId));
}

export function ApartmentsPage() {
  const [apartments, setApartments] = useState<ApartmentSummary[]>([]);
  const [editingApartmentId, setEditingApartmentId] = useState<string | null>(null);
  const [editingTimezone, setEditingTimezone] = useState("UTC");
  const [savingTimezone, setSavingTimezone] = useState(false);
  const [message, setMessage] = useState("");
  const [qrApartmentId, setQrApartmentId] = useState<string | null>(null);

  const load = async (cancelled?: { value: boolean }) => {
    try {
      const [apartmentRows, devices, codes] = await Promise.all([
        api.listApartmentTimezones(getAdminToken()),
        api.listDevices(getAdminToken()),
        api.listAccessCodes(getAdminToken()),
      ]);

      if (!cancelled || !cancelled.value) {
        setApartments(summarizeApartments(apartmentRows, devices, codes));
        setMessage("");
      }
    } catch (error) {
      if (!cancelled || !cancelled.value) {
        setMessage(error instanceof Error ? error.message : "Failed to load apartments.");
      }
    }
  };

  useEffect(() => {
    const cancelled = { value: false };

    void load(cancelled);
    return () => {
      cancelled.value = true;
    };
  }, []);

  const onStartEditTimezone = (apartment: ApartmentSummary) => {
    setEditingApartmentId(apartment.apartmentId);
    setEditingTimezone(apartment.timezone || "UTC");
    setMessage("");
  };

  const onCancelEditTimezone = () => {
    setEditingApartmentId(null);
    setEditingTimezone("UTC");
  };

  const onSaveTimezone = async (apartmentId: string) => {
    const timezone = editingTimezone.trim();
    if (!timezone) {
      setMessage("Timezone cannot be empty.");
      return;
    }

    setSavingTimezone(true);
    setMessage("");
    try {
      await api.updateApartmentTimezone(getAdminToken(), apartmentId, timezone);
      onCancelEditTimezone();
      await load();
      setMessage(`Timezone updated for ${apartmentId}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Timezone update failed.");
    } finally {
      setSavingTimezone(false);
    }
  };

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Apartments</h2>
        <p>See each apartment in one place and open the guest QR link directly.</p>
      </header>

      {message ? <p className="inline-message">{message}</p> : null}

      {apartments.length === 0 && !message ? (
        <p className="inline-message">No apartments found yet. Create a device or access code first.</p>
      ) : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Apartment</th>
              <th>Timezone</th>
              <th>Devices</th>
              <th>Access Codes</th>
              <th>Active Codes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {apartments.map((apartment) => (
              <tr key={apartment.apartmentId}>
                <td>{apartment.apartmentId}</td>
                <td>
                  {editingApartmentId === apartment.apartmentId ? (
                    <input
                      value={editingTimezone}
                      onChange={(event) => setEditingTimezone(event.target.value)}
                      placeholder="Europe/Berlin"
                    />
                  ) : (
                    apartment.timezone
                  )}
                </td>
                <td>{apartment.deviceCount}</td>
                <td>{apartment.codeCount}</td>
                <td>{apartment.activeCodeCount}</td>
                <td>
                  <div className="row-actions">
                    {editingApartmentId === apartment.apartmentId ? (
                      <>
                        <button
                          type="button"
                          onClick={() => void onSaveTimezone(apartment.apartmentId)}
                          disabled={savingTimezone}
                        >
                          {savingTimezone ? "Saving..." : "Save"}
                        </button>
                        <button
                          type="button"
                          onClick={onCancelEditTimezone}
                          disabled={savingTimezone}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => onStartEditTimezone(apartment)}
                          title="Edit apartment timezone"
                        >
                          Edit
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => setQrApartmentId(apartment.apartmentId)}
                      title="Show guest QR code"
                    >
                      QR Code
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {qrApartmentId ? (
        <QrModal
          url={guestUrl(qrApartmentId)}
          apartmentId={qrApartmentId}
          onClose={() => setQrApartmentId(null)}
        />
      ) : null}
    </section>
  );
}