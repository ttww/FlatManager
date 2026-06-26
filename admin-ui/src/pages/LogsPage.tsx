import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatDateTime, statusClass } from "../lib/format";
import { getAdminToken } from "../lib/session";
import type { AccessLogSummary } from "../types";

export function LogsPage() {
  const [rows, setRows] = useState<AccessLogSummary[]>([]);
  const [message, setMessage] = useState("");
  const [clearing, setClearing] = useState(false);

  const load = () =>
    api
      .getRecentLogs(getAdminToken())
      .then(setRows)
      .catch((error) => setMessage(error instanceof Error ? error.message : "Load failed"));

  useEffect(() => { void load(); }, []);

  const onClearAll = async () => {
    if (!window.confirm("Delete all access logs?")) return;
    setClearing(true);
    setMessage("");
    try {
      await api.deleteAllAccessLogs(getAdminToken());
      setRows([]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Clear failed.");
    } finally {
      setClearing(false);
    }
  };

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Access Logs</h2>
        <p>Auditable access outcomes with timestamp, source IP, and command reference.</p>
      </header>

      <div className="panel-actions">
        <button type="button" className="danger" onClick={() => void onClearAll()} disabled={clearing || rows.length === 0}>
          {clearing ? "Clearing..." : "Clear All"}
        </button>
      </div>

      {message ? <p className="inline-message">{message}</p> : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Apartment</th>
              <th>Result</th>
              <th>Reason</th>
              <th>IP</th>
              <th>Command</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{formatDateTime(row.timestamp, row.apartment_timezone)}</td>
                <td>{row.apartment_id}</td>
                <td>
                  <span className={`status-pill ${statusClass(row.result)}`}>{row.result}</span>
                </td>
                <td>{row.reason ?? "-"}</td>
                <td>{row.ip_address}</td>
                <td>{row.command_id ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
