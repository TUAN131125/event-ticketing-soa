import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Activity, LockKeyhole, ShieldCheck, Ticket } from 'lucide-react';
import { AuthProvider, useAuth } from './auth/AuthProvider';
import {
  esbAdminClient,
  type AggregateHealth,
  type BookingResult,
  type PublicEvent,
  type TraceStep,
} from './api/esb';
import './styles/admin.css';

/**
 * Operations areas the ESB public contract does not publish. They are listed so the console
 * states plainly what it cannot do, instead of calling a private service or faking a result.
 */
const UNSUPPORTED_AREAS: { title: string; reason: string }[] = [
  {
    title: 'User and role administration',
    reason:
      'Identity publishes a role-change command, but it requires the target user’s ETag and no operation returns another user’s record. Use the Identity service directly.',
  },
  {
    title: 'Event authoring and publishing',
    reason: 'The ESB public API exposes event reads only; event commands are not published.',
  },
  {
    title: 'Booking, payment, ticket and notification listings',
    reason:
      'The public contract exposes booking lookup by identifier only. Calling the providers directly is not allowed.',
  },
];

function useAccessToken(): string | null {
  return useAuth().session?.accessToken ?? null;
}

function HealthPanel({ accessToken }: { accessToken: string }) {
  const [health, setHealth] = useState<AggregateHealth | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    esbAdminClient
      .health(accessToken)
      .then((value) => alive && setHealth(value))
      .catch((value: Error) => alive && setError(value.message));
    return () => {
      alive = false;
    };
  }, [accessToken]);
  return (
    <section className="card">
      <div className="section-heading">
        <h3>Aggregate health</h3>
        {health && <span className="ui-badge">{health.status}</span>}
      </div>
      {error && <p className="form-error">{error}</p>}
      {health ? (
        <div className="health-list">
          {health.dependencies.map((dependency) => (
            <div className="health-row" key={dependency.name}>
              <span>
                <span
                  className={`status-dot ${dependency.status === 'UP' ? 'is-healthy' : 'is-degraded'}`}
                />
                {dependency.name}
              </span>
              <small>
                {dependency.critical ? 'critical' : 'noncritical'} · {dependency.status}
                {dependency.errorCode ? ` · ${dependency.errorCode}` : ''}
              </small>
            </div>
          ))}
        </div>
      ) : (
        !error && <p className="muted">Loading dependency status…</p>
      )}
    </section>
  );
}

function EventsPanel({ accessToken }: { accessToken: string }) {
  const [events, setEvents] = useState<PublicEvent[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    esbAdminClient
      .events(accessToken)
      .then((value) => alive && setEvents(value))
      .catch((value: Error) => alive && setError(value.message));
    return () => {
      alive = false;
    };
  }, [accessToken]);
  return (
    <section className="card">
      <div className="section-heading">
        <h3>Events</h3>
        <small className="muted">Read-only</small>
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Event</th>
              <th>Venue</th>
              <th>Starts at</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {events.map((item) => (
              <tr key={item.eventId}>
                <td className="table-primary">
                  <strong>{item.name}</strong>
                  <small>{item.eventId}</small>
                </td>
                <td>{item.venue}</td>
                <td>{new Date(item.startsAt).toLocaleString()}</td>
                <td>{item.status}</td>
              </tr>
            ))}
            {events.length === 0 && !error && (
              <tr>
                <td colSpan={4} className="muted">
                  No events published.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BookingPanel({ accessToken }: { accessToken: string }) {
  const [booking, setBooking] = useState<BookingResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const lookup = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    const id = String(new FormData(event.currentTarget).get('bookingId') ?? '').trim();
    if (!id) return;
    setBusy(true);
    void esbAdminClient
      .booking(accessToken, id)
      .then(setBooking)
      .catch((value: Error) => setError(value.message))
      .finally(() => setBusy(false));
  };

  const cancel = () => {
    if (!booking) return;
    setError('');
    setBusy(true);
    void esbAdminClient
      .cancelBooking(accessToken, booking.bookingId)
      .then(setBooking)
      .catch((value: Error) => setError(value.message))
      .finally(() => setBusy(false));
  };

  const settled = booking ? ['CONFIRMED', 'FAILED', 'CANCELLED'].includes(booking.status) : false;

  return (
    <section className="card">
      <div className="section-heading">
        <h3>Booking lookup</h3>
        <small className="muted">By identifier</small>
      </div>
      <form className="toolbar" onSubmit={lookup}>
        <input className="native-input" name="bookingId" aria-label="Booking ID" required />
        <button className="native-button" type="submit" disabled={busy}>
          Look up
        </button>
      </form>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {booking && (
        <>
          <dl className="detail-list">
            <div>
              <dt>Booking</dt>
              <dd>{booking.bookingId}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{booking.status}</dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd>
                {booking.total.amountMinor.toLocaleString()} {booking.total.currency}
              </dd>
            </div>
            <div>
              <dt>Reservation</dt>
              <dd>{booking.reservationId ?? '—'}</dd>
            </div>
            <div>
              <dt>Payment</dt>
              <dd>{booking.paymentId ?? '—'}</dd>
            </div>
            <div>
              <dt>Correlation ID</dt>
              <dd>{booking.correlationId}</dd>
            </div>
          </dl>
          <div className="stack-actions">
            <button className="native-button" onClick={cancel} disabled={busy || settled}>
              Cancel booking
            </button>
            {settled && (
              <small className="muted">This booking has already reached a final state.</small>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function TracePanel({ accessToken }: { accessToken: string }) {
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [error, setError] = useState('');
  const lookup = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    const id = String(new FormData(event.currentTarget).get('correlationId') ?? '').trim();
    if (!id) return;
    void esbAdminClient
      .traces(accessToken, id)
      .then(setSteps)
      .catch((value: Error) => setError(value.message));
  };
  return (
    <section className="card">
      <div className="section-heading">
        <h3>Workflow trace</h3>
        <small className="muted">By correlation ID</small>
      </div>
      <form className="toolbar" onSubmit={lookup}>
        <input className="native-input" name="correlationId" aria-label="Correlation ID" required />
        <button className="native-button" type="submit">
          Look up
        </button>
      </form>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {steps.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Operation</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step, index) => (
                <tr key={`${step.service}-${step.operation}-${index}`}>
                  <td>{step.service}</td>
                  <td>{step.operation}</td>
                  <td>{step.status}</td>
                  <td>{step.durationMs} ms</td>
                  <td>{step.errorCode ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function UnsupportedPanel() {
  return (
    <section className="card">
      <div className="section-heading">
        <h3>Not supported by the current contract</h3>
      </div>
      <ul className="plain-list">
        {UNSUPPORTED_AREAS.map((area) => (
          <li key={area.title}>
            <strong>{area.title}</strong>
            <p className="muted">{area.reason}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Console() {
  const auth = useAuth();
  const accessToken = useAccessToken();
  const signOut = useCallback(() => void auth.logout(), [auth]);

  if (auth.isRestoring) return <p className="route-loading">Restoring session…</p>;
  if (!accessToken) return <Login />;

  return (
    <div className="admin-app-shell">
      <main className="admin-main">
        <header className="admin-topbar">
          <div className="topbar-leading">
            <h1>Operations console</h1>
            <p className="muted">Only operations published by the ESB public API are available.</p>
          </div>
          <div className="topbar-actions">
            <div className="user-details">
              <strong>{auth.user?.email}</strong>
              <small>{auth.user?.roles.join(', ')}</small>
            </div>
            <button className="native-button" onClick={signOut}>
              Sign out
            </button>
          </div>
        </header>
        <div className="admin-content">
          <div className="dashboard-grid">
            <HealthPanel accessToken={accessToken} />
            <EventsPanel accessToken={accessToken} />
            <BookingPanel accessToken={accessToken} />
            <TracePanel accessToken={accessToken} />
            <UnsupportedPanel />
          </div>
        </div>
      </main>
    </div>
  );
}

function Login() {
  const auth = useAuth();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    const values = new FormData(event.currentTarget);
    const email = String(values.get('email') ?? '')
      .trim()
      .toLowerCase();
    const password = String(values.get('password') ?? '');
    if (!email) {
      setError('Enter the administrator email address.');
      return;
    }
    if (password.length < 12) {
      setError('Password must contain at least 12 characters.');
      return;
    }
    setBusy(true);
    void auth
      .login(email, password)
      .catch((value: Error) => setError(value.message))
      .finally(() => setBusy(false));
  };
  return (
    <div className="auth-layout">
      <section className="auth-panel">
        <div className="auth-brand" aria-label="Event Ticketing operations console">
          <span className="brand-mark">
            <Ticket size={18} aria-hidden="true" />
          </span>
          <span>
            <strong>Event Ticketing</strong>
            <small>Operations console</small>
          </span>
        </div>
        <div className="auth-copy">
          <p className="eyebrow">Secure access</p>
          <h1>Run every event with confidence.</h1>
          <p>Sign in with an Identity account that holds the ADMIN role.</p>
        </div>
        <form className="auth-form" onSubmit={submit} noValidate>
          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}
          <label htmlFor="admin-email">
            <span>Email</span>
            <input
              id="admin-email"
              className="native-input"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="admin@example.com"
              aria-label="Email"
              required
            />
          </label>
          <label htmlFor="admin-password">
            <span>Password</span>
            <input
              id="admin-password"
              className="native-input"
              name="password"
              type="password"
              autoComplete="current-password"
              placeholder="At least 12 characters"
              minLength={12}
              aria-label="Password"
              required
            />
          </label>
          <button className="native-button auth-submit" type="submit" disabled={busy}>
            <LockKeyhole size={17} aria-hidden="true" />
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="auth-note">
            <ShieldCheck size={16} aria-hidden="true" /> Access is restricted to authorised
            operators.
          </p>
        </form>
      </section>
      <aside className="auth-aside" aria-label="Operations console capabilities">
        <div className="auth-aside-content">
          <p className="eyebrow">Built for live operations</p>
          <h2>One calm place for the moments that matter.</h2>
          <p>
            Review service health, inspect bookings and follow correlation traces without bypassing
            the ESB contract.
          </p>
          <div className="auth-feature-list">
            <span>
              <Activity size={18} aria-hidden="true" /> Live dependency health
            </span>
            <span>
              <ShieldCheck size={18} aria-hidden="true" /> Contract-safe administration
            </span>
          </div>
        </div>
      </aside>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Console />
    </AuthProvider>
  );
}
