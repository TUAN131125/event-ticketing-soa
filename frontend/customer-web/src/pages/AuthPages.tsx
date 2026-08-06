import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Card, FormField, Input, PasswordInput, Alert } from '@event-ticketing/shared-ui';
import { useAuth } from '../app/auth';
import { ApiError } from '../api/auth-client';
import { ClipboardList, Tickets } from 'lucide-react';
const schema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(12, 'Use at least 12 characters'),
});
type Values = z.infer<typeof schema>;
function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const { signIn, signUp } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [message, setMessage] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const next = new URLSearchParams(location.search).get('next') || '/events';
  const submit = async (values: Values) => {
    setMessage(null);
    try {
      if (mode === 'login') {
        await signIn(values.email, values.password);
        navigate(next, { replace: true });
      } else {
        await signUp(values.email, values.password);
        setMessage('Account created. Sign in to continue.');
        navigate(`/login?email=${encodeURIComponent(values.email)}`);
      }
    } catch (error) {
      const api = error instanceof ApiError ? error : null;
      // Field-level problems belong on the field. Only a transport failure or a 5xx is
      // reported as an unavailable service.
      if (api?.status === 409) {
        form.setError('email', {
          type: 'server',
          message: 'That email is already registered. Sign in instead.',
        });
        return;
      }
      if (api?.status === 422 || api?.status === 400) {
        form.setError('email', {
          type: 'server',
          message: api.message || 'Check the email and password and try again.',
        });
        return;
      }
      if (api?.status === 401) {
        setMessage('That email or password is not correct.');
        return;
      }
      if (api?.code === 'ACCOUNT_LOCKED' || api?.status === 423) {
        setMessage('Your account is temporarily locked. Try again later.');
        return;
      }
      if (api?.code === 'ACCOUNT_DISABLED' || api?.status === 403) {
        setMessage('This account has been disabled. Contact support.');
        return;
      }
      if (api?.code === 'CONFIGURATION_ERROR') {
        setMessage('This build is missing its Identity service URL. Contact an administrator.');
        return;
      }
      if (api && api.status >= 500) {
        setMessage('The authentication service is temporarily unavailable. Try again shortly.');
        return;
      }
      setMessage(api?.message ?? 'We could not complete that request. Please try again.');
    }
  };
  return (
    <section className="container page-section auth-page">
      <div className="auth-intro">
        <p className="eyebrow">{mode === 'login' ? 'Welcome back' : 'Join Evently'}</p>
        <h1>
          {mode === 'login'
            ? 'Sign in to keep your plans close'
            : 'Create an account for your next great night out'}
        </h1>
        <p className="lede">Your account keeps bookings, tickets and live updates together.</p>
      </div>
      <Card padded className="auth-card">
        <form className="stack-form auth-card-form" onSubmit={form.handleSubmit(submit)} noValidate>
          <FormField
            label="Email"
            htmlFor="customer-auth-email"
            error={form.formState.errors.email?.message}
          >
            <Input
              {...form.register('email')}
              id="customer-auth-email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
            />
          </FormField>
          <FormField
            label="Password"
            htmlFor="customer-auth-password"
            hint={mode === 'register' ? 'At least 12 characters.' : undefined}
            error={form.formState.errors.password?.message}
          >
            <PasswordInput
              {...form.register('password')}
              id="customer-auth-password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              placeholder="Your password"
            />
          </FormField>
          {message && (
            <p className="form-error" role="alert">
              {message}
            </p>
          )}
          <Button type="submit" fullWidth disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting
              ? 'Please wait…'
              : mode === 'login'
                ? 'Sign in'
                : 'Create account'}
          </Button>
          <p className="auth-switch">
            {mode === 'login' ? (
              <>
                New to Evently? <Link to="/register">Create an account</Link>
              </>
            ) : (
              <>
                Already have an account? <Link to="/login">Sign in</Link>
              </>
            )}
          </p>
        </form>
      </Card>
    </section>
  );
}
export function LoginPage() {
  return <AuthForm mode="login" />;
}
export function RegisterPage() {
  return <AuthForm mode="register" />;
}
export function AccountPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <section className="container page-section narrow-page">
      <div className="page-heading">
        <p className="eyebrow">Account</p>
        <h1>Your profile</h1>
      </div>
      <div className="account-layout">
        <Card padded>
          <dl className="facts">
            <div>
              <dt>Email</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{user.status}</dd>
            </div>
            <div>
              <dt>Roles</dt>
              <dd>{user.roles.join(', ')}</dd>
            </div>
            <div>
              <dt>Member since</dt>
              <dd>
                {new Intl.DateTimeFormat(undefined, {
                  dateStyle: 'medium',
                }).format(new Date(user.createdAt))}
              </dd>
            </div>
          </dl>
        </Card>
        <Alert tone="info" title="Customer details are collected during checkout">
          This page shows Identity data only. UI-04 collects the customer name, email and phone as a
          validated checkout draft; the backend remains responsible for Customer mapping.
        </Alert>
        <div className="account-actions-grid">
          <Link className="account-action-card" to="/bookings">
            <ClipboardList size={24} />
            <span>
              <strong>My bookings</strong>
              <small>Review authoritative booking status and cancellation results.</small>
            </span>
          </Link>
          <Link className="account-action-card" to="/tickets">
            <Tickets size={24} />
            <span>
              <strong>Ticket wallet</strong>
              <small>Open tickets from confirmed recent bookings.</small>
            </span>
          </Link>
        </div>
      </div>
    </section>
  );
}
