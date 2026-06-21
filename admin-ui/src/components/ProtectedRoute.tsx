import { Navigate, Outlet, useLocation } from "react-router-dom";

import { getAdminToken } from "../lib/session";

export function ProtectedRoute() {
  const location = useLocation();
  const token = getAdminToken();

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
