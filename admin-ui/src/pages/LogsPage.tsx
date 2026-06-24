import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatDateTime, statusClass } from "../lib/format";
import { getAdminToken } from "../lib/session";
import type { AccessLogSummary } from "../types";

export function LogsPage() {
  const [rows, setRows] = useState<AccessLogSummary[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api
      .getRecentLogs(getAdminToken())
      .then(setRows)
      .catch((error) => setMessage(error instanceof Error ? error.message : "Load failed"));
  }, []);

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Access Logs</h2>
        <p>Auditable access outcomes with timestamp, source IP, and command reference.</p>
      </header>

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
