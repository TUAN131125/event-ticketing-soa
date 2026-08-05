import { useState, type ReactNode } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Activity,
  Bell,
  CalendarDays,
  ChevronLeft,
  CircleDollarSign,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Shield,
  Users,
  X,
} from 'lucide-react';
import { Button, IconButton } from '@event-ticketing/shared-ui';
import { useAuth } from '../auth/AuthProvider';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/events', label: 'Events', icon: CalendarDays },
  { to: '/bookings', label: 'Bookings', icon: ClipboardList },
  { to: '/payments', label: 'Payments', icon: CircleDollarSign },
  { to: '/notifications', label: 'Notifications', icon: Bell },
  { to: '/users', label: 'Users & roles', icon: Users },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
];

export function AppShell() {
  const [open, setOpen] = useState(false);
  const { user, logout } = useAuth();
  const location = useLocation();
  const title =
    navItems.find((item) => item.to !== '/' && location.pathname.startsWith(item.to))?.label ??
    'Overview';
  return (
    <div className="admin-app-shell">
      <aside
        className={`admin-sidebar${open ? ' is-open' : ''}`}
        aria-label="Operations navigation"
      >
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">
            ET
          </span>
          <span>
            <strong>Event Ticketing</strong>
            <small>Operations console</small>
          </span>
          <IconButton
            label="Close navigation"
            className="sidebar-close"
            onClick={() => setOpen(false)}
          >
            <X size={18} />
          </IconButton>
        </div>
        <nav className="sidebar-nav">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
              onClick={() => setOpen(false)}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className="status-dot" />
            Services via ESB
          </div>
          <a href="/health" className="sidebar-link">
            <Shield size={18} />
            <span>Service health</span>
          </a>
        </div>
      </aside>
      {open && (
        <button
          className="sidebar-overlay"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="admin-main">
        <header className="admin-topbar">
          <div className="topbar-leading">
            <IconButton
              label="Open navigation"
              className="menu-button"
              onClick={() => setOpen(true)}
            >
              <Menu size={20} />
            </IconButton>
            <div>
              <p className="eyebrow">Operations</p>
              <h1>{title}</h1>
            </div>
          </div>
          <div className="topbar-actions">
            <Button
              variant="ghost"
              size="sm"
              icon={<Search size={17} />}
              onClick={() => window.dispatchEvent(new CustomEvent('admin:focus-search'))}
            >
              Search
            </Button>
            <div className="user-menu">
              <span className="avatar" aria-hidden="true">
                {(user?.displayName ?? user?.email ?? 'A').slice(0, 1).toUpperCase()}
              </span>
              <span className="user-details">
                <strong>{user?.displayName || user?.email || 'Admin'}</strong>
                <small>{user?.roles.join(' · ')}</small>
              </span>
              <Button
                variant="ghost"
                size="sm"
                icon={<LogOut size={16} />}
                onClick={() => void logout()}
              >
                Sign out
              </Button>
            </div>
          </div>
        </header>
        <main className="admin-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
        {description && <p className="page-description">{description}</p>}
        {children}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function BackLink({ to, children = 'Back' }: { to: string; children?: ReactNode }) {
  return (
    <NavLink to={to} className="back-link">
      <ChevronLeft size={16} />
      {children}
    </NavLink>
  );
}
