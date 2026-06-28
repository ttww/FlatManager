import { useEffect, useMemo, useState } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import "./admin.css";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Sidebar } from "./components/Sidebar";
import { getBrowserTimezone, type TimezoneDisplayMode } from "./lib/format";
import { ApartmentsPage } from "./pages/ApartmentsPage";
import { CodesPage } from "./pages/CodesPage";
import { CommandsPage } from "./pages/CommandsPage";
import { DevicesPage } from "./pages/DevicesPage";
import { LoginPage } from "./pages/LoginPage";
import { LogsPage } from "./pages/LogsPage";
import { SupportPage } from "./pages/SupportPage";

const TIMEZONE_DISPLAY_MODE_KEY = "admin-timezone-display-mode";

function resolveInitialDisplayMode(): TimezoneDisplayMode {
  const stored = window.localStorage.getItem(TIMEZONE_DISPLAY_MODE_KEY);
  return stored === "apartment" ? "apartment" : "local";
}

type AdminLayoutProps = {
  browserTimezone: string;
  timezoneDisplayMode: TimezoneDisplayMode;
  onTimezoneDisplayModeChange: (mode: TimezoneDisplayMode) => void;
};

function AdminLayout({
  browserTimezone,
  timezoneDisplayMode,
  onTimezoneDisplayModeChange,
}: AdminLayoutProps) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="content-shell">
        <section className="timezone-toolbar" aria-label="Timezone display mode">
          <p className="tiny muted">Time display: {timezoneDisplayMode === "local" ? `Local (${browserTimezone})` : "Apartment timezone"}</p>
          <div className="timezone-toggle" role="group" aria-label="Select timezone mode">
            <button
              type="button"
              className={timezoneDisplayMode === "local" ? "active" : ""}
              onClick={() => onTimezoneDisplayModeChange("local")}
            >
              Local
            </button>
            <button
              type="button"
              className={timezoneDisplayMode === "apartment" ? "active" : ""}
              onClick={() => onTimezoneDisplayModeChange("apartment")}
            >
              Apartment
            </button>
          </div>
        </section>
        <Outlet />
      </main>
    </div>
  );
}

function App() {
  const browserTimezone = useMemo(() => getBrowserTimezone(), []);
  const [timezoneDisplayMode, setTimezoneDisplayMode] = useState<TimezoneDisplayMode>(() => resolveInitialDisplayMode());

  useEffect(() => {
    window.localStorage.setItem(TIMEZONE_DISPLAY_MODE_KEY, timezoneDisplayMode);
  }, [timezoneDisplayMode]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <AdminLayout
              browserTimezone={browserTimezone}
              timezoneDisplayMode={timezoneDisplayMode}
              onTimezoneDisplayModeChange={setTimezoneDisplayMode}
            />
          }
        >
          <Route path="/" element={<Navigate to="/codes" replace />} />
          <Route path="/apartments" element={<ApartmentsPage />} />
          <Route
            path="/codes"
            element={<CodesPage timezoneDisplayMode={timezoneDisplayMode} browserTimezone={browserTimezone} />}
          />
          <Route
            path="/devices"
            element={<DevicesPage timezoneDisplayMode={timezoneDisplayMode} browserTimezone={browserTimezone} />}
          />
          <Route
            path="/commands"
            element={<CommandsPage timezoneDisplayMode={timezoneDisplayMode} browserTimezone={browserTimezone} />}
          />
          <Route
            path="/logs"
            element={<LogsPage timezoneDisplayMode={timezoneDisplayMode} browserTimezone={browserTimezone} />}
          />
          <Route path="/support" element={<SupportPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
