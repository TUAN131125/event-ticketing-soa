import { useState, type FormEvent } from 'react';
import { Activity, LockKeyhole, ShieldCheck, Ticket } from 'lucide-react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';

export function LoginPage() {
  const auth = useAuth();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (auth.session?.accessToken) return <Navigate to="/overview" replace />;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    const values = new FormData(event.currentTarget);
    const email = String(values.get('email') ?? '').trim().toLowerCase();
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
      .then(() => {
        if (!auth.user?.roles?.includes('ADMIN')) {
          // The API must still enforce ADMIN. This message is only a frontend guard.
        }
      })
      .catch((value: Error) => setError(value.message))
      .finally(() => setBusy(false));
  };

  return (
    <div className="auth-layout">
      <section className="auth-panel">
        <div className="auth-brand" aria-label="Event Ticketing operations console">
          <span className="brand-mark"><Ticket size={18} aria-hidden="true" /></span>
          <span><strong>Event Ticketing</strong><small>Operations console</small></span>
        </div>
        <div className="auth-copy">
          <p className="eyebrow">Secure access</p>
          <h1>Run every event with confidence.</h1>
          <p>Sign in with an Identity account that holds the ADMIN role.</p>
        </div>
        <form className="auth-form" onSubmit={submit} noValidate>
          {error && <div className="auth-error" role="alert">{error}</div>}
          <label htmlFor="admin-email">
            <span>Email</span>
            <input id="admin-email" className="native-input" name="email" type="email" autoComplete="email" placeholder="admin@example.com" required />
          </label>
          <label htmlFor="admin-password">
            <span>Password</span>
            <input id="admin-password" className="native-input" name="password" type="password" autoComplete="current-password" placeholder="At least 12 characters" minLength={12} required />
          </label>
          <button className="native-button auth-submit" type="submit" disabled={busy}>
            <LockKeyhole size={17} aria-hidden="true" />
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="auth-note"><ShieldCheck size={16} aria-hidden="true" /> Access is restricted to authorised operators.</p>
        </form>
      </section>
      <aside className="auth-aside" aria-label="Operations console capabilities">
        <div className="auth-aside-content">
          <p className="eyebrow">Operations workspace</p>
          <h2>Dedicated routes for each administration area.</h2>
          <p>Connected pages use the current ESB contract. Pending pages state their backend dependencies without bypassing service boundaries.</p>
          <div className="auth-feature-list">
            <span><Activity size={18} aria-hidden="true" /> Live dependency health</span>
            <span><ShieldCheck size={18} aria-hidden="true" /> Contract-safe administration</span>
          </div>
        </div>
      </aside>
    </div>
  );
}
