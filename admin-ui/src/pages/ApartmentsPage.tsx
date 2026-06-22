import { useEffect, useState } from "react";

import { QrModal } from "../components/QrModal";
import { api } from "../lib/api";
import { getAdminToken } from "../lib/session";
import type { AccessCodeSummary, AdminDevice } from "../types";

type ApartmentSummary = {
  apartmentId: string;
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

function summarizeApartments(devices: AdminDevice[], codes: AccessCodeSummary[]): ApartmentSummary[] {
  const byApartment = new Map<string, ApartmentSummary>();

  for (const device of devices) {
    const current = byApartment.get(device.apartment_id) ?? {
      apartmentId: device.apartment_id,
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
  const [message, setMessage] = useState("");
  const [qrApartmentId, setQrApartmentId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [devices, codes] = await Promise.all([
          api.listDevices(getAdminToken()),
          api.listAccessCodes(getAdminToken()),
        ]);

        if (!cancelled) {
          setApartments(summarizeApartments(devices, codes));
          setMessage("");
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "Failed to load apartments.");
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

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
                <td>{apartment.deviceCount}</td>
                <td>{apartment.codeCount}</td>
                <td>{apartment.activeCodeCount}</td>
                <td>
                  <div className="row-actions">
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