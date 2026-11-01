import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Video,
  History as HistoryIcon,
  Settings as SettingsIcon,
  LogOut,
  User as UserIcon,
  Cpu,
  ChevronDown,
  ShieldAlert,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { getAiStatus, AIStatus } from "../api/live";

export default function Layout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, isAuthenticated, signOut } = useAuth();
  const isLanding = pathname === "/";

  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  useEffect(() => {
    let active = true;
    getAiStatus()
      .then((st) => {
        if (active) setAiStatus(st);
      })
      .catch(() => {
        // AI status endpoint degraded or offline
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSignOut = () => {
    signOut();
    setUserMenuOpen(false);
    navigate("/");
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <header className="site-header">
        <div className="container header-inner">
          <Link to="/" className="brand" aria-label="Sensora AI home">
            <span className="brand-icon">
              <Cpu size={20} />
            </span>
            <span className="brand-text">
              Sensora <b>AI</b>
            </span>
          </Link>

          {isLanding ? (
            <nav className="nav" aria-label="Primary navigation">
              <a href="#how">How it works</a>
              <a href="#capabilities">Capabilities</a>
              {isAuthenticated ? (
                <NavLink to="/dashboard" className="nav-highlight">
                  Dashboard
                </NavLink>
              ) : (
                <Link to="/signin">Sign in</Link>
              )}
            </nav>
          ) : (
            <nav className="nav" aria-label="Application navigation">
              <NavLink
                to="/dashboard"
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                <LayoutDashboard size={17} />
                <span>Dashboard</span>
              </NavLink>
              <NavLink
                to="/live"
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                <Video size={17} />
                <span>Live Assist</span>
              </NavLink>
              <NavLink
                to="/history"
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                <HistoryIcon size={17} />
                <span>History</span>
              </NavLink>
              <NavLink
                to="/settings"
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                <SettingsIcon size={17} />
                <span>Settings</span>
              </NavLink>
            </nav>
          )}

          <div className="header-end">
            {/* Honest AI mode indicator */}
            {aiStatus && (
              <div
                className={`ai-mode-badge ${
                  aiStatus.simulated ? "ai-mode-demo" : "ai-mode-live"
                }`}
                title={aiStatus.note || (aiStatus.simulated ? "Simulated responses for demo & offline testing" : "Live Meta AI inference active")}
              >
                <span className="ai-mode-dot" />
                <span className="ai-mode-text">
                  {aiStatus.simulated ? "SIMULATED AI" : "META AI LIVE"}
                </span>
              </div>
            )}

            {isAuthenticated ? (
              <div className="user-menu-container">
                <button
                  type="button"
                  className="user-profile-button"
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  aria-expanded={userMenuOpen}
                  aria-haspopup="true"
                >
                  <div className="user-avatar">
                    <UserIcon size={15} />
                  </div>
                  <span className="user-display-name">
                    {user?.displayName || "Account"}
                  </span>
                  {user?.kind === "guest" && (
                    <span className="badge badge-guest">Guest</span>
                  )}
                  <ChevronDown size={14} className="text-slate-400" />
                </button>

                {userMenuOpen && (
                  <>
                    <div
                      className="menu-backdrop"
                      onClick={() => setUserMenuOpen(false)}
                    />
                    <div className="user-dropdown-card">
                      <div className="user-dropdown-info">
                        <p className="user-info-name">
                          {user?.displayName || "User"}
                        </p>
                        <p className="user-info-email">
                          {user?.email || (user?.kind === "guest" ? "Temporary Browser Session" : "")}
                        </p>
                      </div>
                      <div className="user-dropdown-divider" />
                      <Link
                        to="/settings"
                        className="user-dropdown-item"
                        onClick={() => setUserMenuOpen(false)}
                      >
                        <SettingsIcon size={16} />
                        <span>Account & Preferences</span>
                      </Link>
                      <button
                        type="button"
                        className="user-dropdown-item text-danger"
                        onClick={handleSignOut}
                      >
                        <LogOut size={16} />
                        <span>Sign out</span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="auth-buttons">
                <Link to="/signin" className="btn btn-secondary btn-small">
                  Sign in
                </Link>
                <Link to="/signup" className="btn btn-primary btn-small">
                  Get Started
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      <main id="main" className="app-content">
        <Outlet />
      </main>

      <footer className="site-footer">
        <div className="container">
          <div className="footer-left">
            <span className="footer-brand">Sensora AI</span>
            <span className="footer-sep">·</span>
            <span className="muted">
              Real-world camera-assisted troubleshooting guidance
            </span>
          </div>
          <div className="footer-disclaimer">
            <ShieldAlert size={14} className="flex-shrink-0" />
            <span>
              Sensora AI is an assistance tool, not a substitute for a licensed professional. If you detect gas, smoke, sparks, or risk of electric shock, immediately stop and contact emergency services.
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
