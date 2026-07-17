import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Home", end: true },
  { to: "/scans/new", label: "New scan", end: false },
  { to: "/scans", label: "History", end: true },
  { to: "/status", label: "Status", end: false },
];

export function AppNavigation() {
  return (
    <header className="site-header">
      <nav className="site-navigation" aria-label="Primary navigation">
        <NavLink className="site-brand" to="/">
          Local SKU Dimensioner
        </NavLink>
        <div className="site-navigation__links">
          {links.map((link) => (
            <NavLink
              key={link.to}
              className={({ isActive }) =>
                isActive ? "site-navigation__link site-navigation__link--active" : "site-navigation__link"
              }
              end={link.end}
              to={link.to}
            >
              {link.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </header>
  );
}
