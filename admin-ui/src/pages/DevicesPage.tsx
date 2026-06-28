import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { QrModal } from "../components/QrModal";
import { api } from "../lib/api";
import { formatDateTime, getDisplayTimezone, statusClass, type TimezoneDisplayMode } from "../lib/format";
import { guestUrl } from "../lib/guestUrl";
import { getAdminToken } from "../lib/session";
import type { AdminDevice, ApartmentTimezone, NewDeviceResponse, RotateDeviceTokenResponse } from "../types";

type DevicesPageProps = {
  timezoneDisplayMode: TimezoneDisplayMode;
  browserTimezone: string;
};

export function DevicesPage({ timezoneDisplayMode, browserTimezone }: DevicesPageProps) {
  const [devices, setDevices] = useState<AdminDevice[]>([]);
  const [apartmentIds, setApartmentIds] = useState<string[]>([]);
  const [apartmentId, setApartmentId] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [editingDeviceId, setEditingDeviceId] = useState<number | null>(null);
  const [editApartmentId, setEditApartmentId] = useState("");
  const [editDeviceName, setEditDeviceName] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const [lastCreated, setLastCreated] = useState<NewDeviceResponse | null>(null);
  const [lastRotated, setLastRotated] = useState<RotateDeviceTokenResponse | null>(null);
  const [message, setMessage] = useState("");
  const [qrApartmentId, setQrApartmentId] = useState<string | null>(null);

  const load = async () => {
    try {
      const rows = await api.listDevices(getAdminToken());
      setDevices(rows);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load devices");
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    api
      .listApartmentTimezones(getAdminToken())
      .then((rows: ApartmentTimezone[]) => setApartmentIds(rows.map((r) => r.apartment_id)))
      .catch(() => setApartmentIds([]));
  }, []);

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("");

    try {
      const created = await api.createDevice(getAdminToken(), {
        apartment_id: apartmentId,
        device_name: deviceName,
      });
      setLastCreated(created);
      setApartmentId("");
      setDeviceName("");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Create failed");
    }
  };

  const onRotate = async (deviceId: number) => {
    setMessage("");
    try {
      const rotated = await api.rotateDeviceToken(getAdminToken(), deviceId);
      setLastRotated(rotated);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Rotate failed");
    }
  };

  const onDelete = async (deviceId: number) => {
    if (!window.confirm("Delete this device?")) return;

    setMessage("");
    try {
      await api.deleteDevice(getAdminToken(), deviceId);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Delete failed");
    }
  };

  const onStartEdit = (device: AdminDevice) => {
    setEditingDeviceId(device.id);
    setEditApartmentId(device.apartment_id);
    setEditDeviceName(device.device_name);
    setMessage("");
  };

  const onCancelEdit = () => {
    setEditingDeviceId(null);
    setEditApartmentId("");
    setEditDeviceName("");
  };

  const onSaveEdit = async (deviceId: number) => {
    const nextApartmentId = editApartmentId.trim();
    const nextDeviceName = editDeviceName.trim();

    if (!nextApartmentId || !nextDeviceName) {
      setMessage("Apartment ID and device name are required.");
      return;
    }

    setEditBusy(true);
    setMessage("");
    try {
      await api.updateDevice(getAdminToken(), deviceId, {
        apartment_id: nextApartmentId,
        device_name: nextDeviceName,
      });
      onCancelEdit();
      await load();
      setMessage("Device updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Update failed");
    } finally {
      setEditBusy(false);
    }
  };

  const displayTimezone = (apartmentTimezone: string) =>
    getDisplayTimezone(timezoneDisplayMode, apartmentTimezone, browserTimezone);

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Devices</h2>
        <p>Provision, rotate tokens, and remove ESP devices by apartment.</p>
      </header>

      <form onSubmit={onCreate} className="device-form">
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
        <input
          value={deviceName}
          onChange={(event) => setDeviceName(event.target.value)}
          placeholder="Device name"
          required
        />
        <button type="submit" className="primary-button">
          Create Device
        </button>
      </form>

      {lastCreated ? (
        <div className="token-card">
          <strong>One-time token (store securely):</strong>
          <code>{lastCreated.raw_token}</code>
        </div>
      ) : null}

      {lastRotated ? (
        <div className="token-card">
          <strong>Rotated token for device #{lastRotated.id}:</strong>
          <code>{lastRotated.raw_token}</code>
        </div>
      ) : null}

      {message ? <p className="inline-message">{message}</p> : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Apartment</th>
              <th>Name</th>
              <th>Status</th>
              <th>Last Seen</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => (
              <tr key={device.id}>
                <td>{device.id}</td>
                <td>
                  {editingDeviceId === device.id ? (
                    <select
                      value={editApartmentId}
                      onChange={(event) => setEditApartmentId(event.target.value)}
                    >
                      <option value="">— select apartment —</option>
                      {apartmentIds.map((id) => (
                        <option key={id} value={id}>{id}</option>
                      ))}
                    </select>
                  ) : (
                    device.apartment_id
                  )}
                </td>
                <td>
                  {editingDeviceId === device.id ? (
                    <input
                      value={editDeviceName}
                      onChange={(event) => setEditDeviceName(event.target.value)}
                    />
                  ) : (
                    device.device_name
                  )}
                </td>
                <td>
                  <span className={`status-pill ${statusClass(device.status)}`}>{device.status}</span>
                </td>
                <td>{formatDateTime(device.last_seen, displayTimezone(device.apartment_timezone))}</td>
                <td>
                  <div className="row-actions">
                    {editingDeviceId === device.id ? (
                      <>
                        <button
                          type="button"
                          onClick={() => void onSaveEdit(device.id)}
                          disabled={editBusy}
                        >
                          {editBusy ? "Saving..." : "Save"}
                        </button>
                        <button type="button" onClick={onCancelEdit} disabled={editBusy}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => setQrApartmentId(device.apartment_id)}
                          title="Show guest QR code"
                        >
                          QR Code
                        </button>
                        <button type="button" onClick={() => onStartEdit(device)}>
                          Edit
                        </button>
                        <button type="button" onClick={() => void onRotate(device.id)}>
                          Rotate Token
                        </button>
                        <button type="button" className="danger" onClick={() => void onDelete(device.id)}>
                          Delete
                        </button>
                      </>
                    )}
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
