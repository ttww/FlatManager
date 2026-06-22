import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import "./admin.css";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Sidebar } from "./components/Sidebar";
import { ApartmentsPage } from "./pages/ApartmentsPage";
import { CodesPage } from "./pages/CodesPage";
import { CommandsPage } from "./pages/CommandsPage";
import { DevicesPage } from "./pages/DevicesPage";
import { LoginPage } from "./pages/LoginPage";
import { LogsPage } from "./pages/LogsPage";
import { SupportPage } from "./pages/SupportPage";

function AdminLayout() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="content-shell">
        <Outlet />
      </main>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AdminLayout />}>
          <Route path="/" element={<Navigate to="/codes" replace />} />
          <Route path="/apartments" element={<ApartmentsPage />} />
          <Route path="/codes" element={<CodesPage />} />
          <Route path="/devices" element={<DevicesPage />} />
          <Route path="/commands" element={<CommandsPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/support" element={<SupportPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
