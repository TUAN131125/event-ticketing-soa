import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { CalendarDays, Menu, Ticket, Tickets, UserCircle, X, LogOut } from 'lucide-react';
import { Button, Drawer, IconButton, ToastProvider } from '@event-ticketing/shared-ui';
import { useAuth } from './auth';

export function Shell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const close = () => setMobileOpen(false);
  const logout = async () => {
    await signOut();
    navigate('/');
  };
  return (
    <ToastProvider>
      <div className="app-shell">
        <header className="site-header">
          <div className="container header-inner">
            <Link to="/" className="brand" aria-label="Evently home">
              <span className="brand-mark">
                <Ticket size={19} />
              </span>
              <span>Evently</span>
            </Link>
            <nav className="desktop-nav" aria-label="Primary navigation">
              <NavLink to="/events" className="nav-link">
                Discover events
              </NavLink>
              {user && (
                <>
                  <NavLink to="/bookings" className="nav-link">
                    My bookings
                  </NavLink>
                  <NavLink to="/tickets" className="nav-link">
                    My tickets
                  </NavLink>
                </>
              )}
            </nav>
            <div className="header-actions desktop-nav">
              {user ? (
                <>
                  <Link to="/account" className="account-link">
                    <UserCircle size={18} /> <span>{user.email}</span>
                  </Link>
                  <Button variant="ghost" size="sm" onClick={() => void logout()}>
                    <LogOut size={16} /> Sign out
                  </Button>
                </>
              ) : (
                <>
                  <Link to="/login" className="nav-link">
                    Sign in
                  </Link>
                  <Link to="/register" className="button button-sm button-primary">
                    Create account
                  </Link>
                </>
              )}
            </div>
            <IconButton
              className="mobile-menu-button"
              label={mobileOpen ? 'Close menu' : 'Open menu'}
              onClick={() => setMobileOpen((value) => !value)}
            >
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </IconButton>
          </div>
        </header>
        <Drawer open={mobileOpen} onClose={close} title="Menu">
          <nav className="mobile-nav">
            <NavLink onClick={close} to="/events" className="nav-link">
              <CalendarDays size={18} /> Discover events
            </NavLink>
            {user && (
              <>
                <NavLink onClick={close} to="/bookings" className="nav-link">
                  <Ticket size={18} /> My bookings
                </NavLink>
                <NavLink onClick={close} to="/tickets" className="nav-link">
                  <Tickets size={18} /> My tickets
                </NavLink>
                <NavLink onClick={close} to="/account" className="nav-link">
                  <UserCircle size={18} /> Account
                </NavLink>
                <Button
                  variant="ghost"
                  onClick={() => {
                    close();
                    void logout();
                  }}
                >
                  <LogOut size={18} /> Sign out
                </Button>
              </>
            )}
            {!user && (
              <>
                <NavLink onClick={close} to="/login" className="nav-link">
                  Sign in
                </NavLink>
                <NavLink onClick={close} to="/register" className="nav-link">
                  Create account
                </NavLink>
              </>
            )}
          </nav>
        </Drawer>
        <main>
          <Outlet />
        </main>
        <footer className="site-footer">
          <div className="container footer-inner">
            <div>
              <span className="brand">
                <span className="brand-mark">
                  <Ticket size={16} />
                </span>{' '}
                Evently
              </span>
              <p>Make room for the moments you will remember.</p>
            </div>
            <div className="footer-links">
              <Link to="/events">Events</Link>
              <Link to="/bookings">Bookings</Link>
              <Link to="/tickets">Tickets</Link>
              <a href="mailto:hello@example.com">Support</a>
            </div>
          </div>
        </footer>
      </div>
    </ToastProvider>
  );
}
