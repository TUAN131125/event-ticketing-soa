import { useCallback, useMemo, useState } from 'react';
import { LogOut, Menu, ShieldAlert, Ticket, X } from 'lucide-react';
import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { NAV_ITEMS, type NavigationGroup } from './navigation';

export function AdminShell() {
  const auth = useAuth();
  const location = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const signOut = useCallback(() => void auth.logout(), [auth]);
  const active = useMemo(
    () => NAV_ITEMS.find((item) => location.pathname.startsWith(item.path)) ?? NAV_ITEMS[0],
    [location.pathname],
  );

  if (auth.isRestoring) return <p className="route-loading">Restoring session…</p>;
  if (!auth.session?.accessToken) return <Navigate to="/login" replace />;

  if (!auth.user?.roles.includes('ADMIN')) {
    return (
      <main className="admin-access-denied">
        <ShieldAlert size={40} />
        <h1>Administrator access required</h1>
        <p>This Identity account does not contain the ADMIN role.</p>
        <button className="native-button" onClick={signOut}>Sign out</button>
      </main>
    );
  }

  return (
    <div className="admin-app-shell">
      <aside className={`admin-sidebar ${mobileNavOpen ? 'is-open' : ''}`}>
        <div className="admin-brand">
          <span className="brand-mark"><Ticket size={18} /></span>
          <span><strong>Evently</strong><small>Operations</small></span>
        </div>
        <nav aria-label="Operations navigation">
          {(['Monitor', 'Operate'] as NavigationGroup[]).map((group) => (
            <div className="nav-group" key={group}>
              <span className="nav-group__label">{group}</span>
              {NAV_ITEMS.filter((item) => item.group === group).map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    to={item.path}
                    className={({ isActive }) => (isActive ? 'is-active' : undefined)}
                    key={item.path}
                    onClick={() => setMobileNavOpen(false)}
                  >
                    <Icon size={18} />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>
      {mobileNavOpen && (
        <button
          className="sidebar-backdrop"
          onClick={() => setMobileNavOpen(false)}
          aria-label="Close navigation"
        />
      )}
      <main className="admin-main">
        <header className="admin-topbar">
          <button
            className="mobile-nav-toggle"
            type="button"
            onClick={() => setMobileNavOpen((value) => !value)}
            aria-label="Toggle navigation"
          >
            {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="topbar-leading">
            <p className="eyebrow">{active.group}</p>
            <h1>{active.label}</h1>
          </div>
          <div className="topbar-actions">
            <div className="user-details">
              <strong>{auth.user?.email}</strong>
              <small>{auth.user?.roles.join(', ')}</small>
            </div>
            <button className="native-button secondary-button" onClick={signOut}>
              <LogOut size={16} /> Sign out
            </button>
          </div>
        </header>
        <div className="admin-content">
          <Outlet context={{ accessToken: auth.session.accessToken }} />
        </div>
      </main>
    </div>
  );
}
