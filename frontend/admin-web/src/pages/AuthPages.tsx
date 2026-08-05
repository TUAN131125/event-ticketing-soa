import { useState } from 'react';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { Alert, Button, FormField, Input, PasswordInput } from '@event-ticketing/shared-ui';
import { useAuth } from '../auth/AuthProvider';
import { ApiError } from '../api/http';

const schema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(12, 'Use at least 12 characters'),
});
type FormValues = z.infer<typeof schema>;
export function AdminLoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [serverError, setServerError] = useState('');
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  });
  const submit = async (values: FormValues) => {
    setServerError('');
    try {
      await login(values.email, values.password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || '/', { replace: true });
    } catch (error) {
      const apiError = error instanceof ApiError ? error : undefined;
      setServerError(
        apiError?.code === 'ACCOUNT_LOCKED'
          ? 'This account is temporarily locked. Try again later.'
          : apiError?.code === 'ACCOUNT_DISABLED'
            ? 'This account has been disabled. Contact an administrator.'
            : 'Unable to sign in with those credentials.',
      );
    }
  };
  return (
    <div className="auth-layout">
      <div className="auth-panel">
        <div className="auth-brand">
          <span className="brand-mark">ET</span>
          <span>
            <strong>Event Ticketing</strong>
            <small>Operations console</small>
          </span>
        </div>
        <div className="auth-copy">
          <p className="eyebrow">Secure access</p>
          <h1>Run every event with confidence.</h1>
          <p>
            Sign in with an administrator or operator account to manage events, bookings and service
            health.
          </p>
        </div>
        <form className="auth-form" onSubmit={form.handleSubmit(submit)} noValidate>
          <FormField
            label="Email"
            htmlFor="admin-auth-email"
            error={form.formState.errors.email?.message}
          >
            <Input
              id="admin-auth-email"
              type="email"
              autoComplete="username"
              {...form.register('email')}
            />
          </FormField>
          <FormField
            label="Password"
            htmlFor="admin-auth-password"
            error={form.formState.errors.password?.message}
          >
            <PasswordInput
              id="admin-auth-password"
              autoComplete="current-password"
              {...form.register('password')}
            />
          </FormField>
          {serverError && <Alert tone="danger">{serverError}</Alert>}
          <Button
            type="submit"
            fullWidth
            loading={form.formState.isSubmitting}
            icon={<ArrowRight size={17} />}
          >
            Sign in
          </Button>
        </form>
        <p className="auth-note">
          <ShieldCheck size={16} /> Sessions use short-lived access tokens and rotating refresh
          sessions.
        </p>
        <p className="auth-link">
          <Link to="/">Return to sign-in help</Link>
        </p>
      </div>
      <div className="auth-aside">
        <p className="eyebrow">Built for live operations</p>
        <h2>One calm place for the moments that matter.</h2>
        <p>
          Keep inventory, payments and customer care aligned as tickets move from publish to
          check-in.
        </p>
      </div>
    </div>
  );
}
