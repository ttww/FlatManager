import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatDateTime, statusClass } from "../lib/format";
import { getAdminToken } from "../lib/session";
import type { CommandSummary } from "../types";

export function CommandsPage() {
  const [rows, setRows] = useState<CommandSummary[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api
      .getRecentCommands(getAdminToken())
      .then(setRows)
      .catch((error) => setMessage(error instanceof Error ? error.message : "Load failed"));
  }, []);

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Command History</h2>
        <p>Recent door command states from pending through acknowledged.</p>
      </header>

      {message ? <p className="inline-message">{message}</p> : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Apartment</th>
              <th>Device</th>
              <th>Status</th>
              <th>Created</th>
              <th>Expires</th>
              <th>Acknowledged</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>{row.apartment_id}</td>
                <td>{row.device_id}</td>
                <td>
                  <span className={`status-pill ${statusClass(row.status)}`}>{row.status}</span>
                </td>
                <td>{formatDateTime(row.created_at, row.apartment_timezone)}</td>
                <td>{formatDateTime(row.expires_at, row.apartment_timezone)}</td>
                <td>{formatDateTime(row.acknowledged_at, row.apartment_timezone)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
