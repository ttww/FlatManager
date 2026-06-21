import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { api } from "../lib/api";
import { formatDateTime, statusClass } from "../lib/format";
import { getAdminToken } from "../lib/session";
import type { AdminDevice, NewDeviceResponse, RotateDeviceTokenResponse } from "../types";

export function DevicesPage() {
  const [devices, setDevices] = useState<AdminDevice[]>([]);
  const [apartmentId, setApartmentId] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [lastCreated, setLastCreated] = useState<NewDeviceResponse | null>(null);
  const [lastRotated, setLastRotated] = useState<RotateDeviceTokenResponse | null>(null);
  const [message, setMessage] = useState("");

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

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Devices</h2>
        <p>Provision, rotate tokens, and remove ESP devices by apartment.</p>
      </header>

      <form onSubmit={onCreate} className="device-form">
        <input
          value={apartmentId}
          onChange={(event) => setApartmentId(event.target.value)}
          placeholder="Apartment ID"
          required
        />
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
                <td>{device.apartment_id}</td>
                <td>{device.device_name}</td>
                <td>
                  <span className={`status-pill ${statusClass(device.status)}`}>{device.status}</span>
                </td>
                <td>{formatDateTime(device.last_seen)}</td>
                <td>
                  <div className="row-actions">
                    <button type="button" onClick={() => void onRotate(device.id)}>
                      Rotate Token
                    </button>
                    <button type="button" className="danger" onClick={() => void onDelete(device.id)}>
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
