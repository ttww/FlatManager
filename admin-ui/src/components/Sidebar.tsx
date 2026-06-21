import { NavLink, useNavigate } from "react-router-dom";

import { clearAdminToken } from "../lib/session";

const links = [
  { to: "/codes", label: "Access Codes" },
  { to: "/devices", label: "Devices" },
  { to: "/commands", label: "Commands" },
  { to: "/logs", label: "Access Logs" },
  { to: "/support", label: "Support" },
];

export function Sidebar() {
  const navigate = useNavigate();

  const onLogout = () => {
    clearAdminToken();
    navigate("/login", { replace: true });
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="chip">FlatManager</span>
        <h1>Admin Console</h1>
      </div>

      <nav className="menu">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => `menu-link ${isActive ? "active" : ""}`}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>

      <button type="button" className="ghost-button" onClick={onLogout}>
        Logout
      </button>
    </aside>
  );
}
