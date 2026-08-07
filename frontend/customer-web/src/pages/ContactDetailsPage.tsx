import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, Mail, Phone, UserRound } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { Alert, Button, Card, FormField, Input } from '@event-ticketing/shared-ui';
import { useAuth } from '../app/auth';
import { useEsb } from '../app/hooks';
import { ApiErrorDetails } from '../components/common/ApiErrorDetails';
import { readCheckoutDraft, writeCheckoutDraft, type CheckoutDraft } from '../utils/checkout-draft';

const contactSchema = z.object({
  fullName: z.string().trim().min(2, 'Enter the customer name').max(120),
  email: z.string().trim().email('Enter a valid email address'),
  phone: z
    .string()
    .trim()
    .min(8, 'Enter a valid phone number')
    .max(20)
    .regex(/^\+?[0-9 ()-]+$/, 'Use digits and an optional country code'),
});

type ContactValues = z.infer<typeof contactSchema>;
type ContactRouteState = Pick<CheckoutDraft, 'eventId' | 'eventName' | 'seatIds'>;

const genericSubmitError =
  'Customer Service rejected or could not complete the onboarding request.';

/**
 * A caught throw is `unknown` and is not renderable on its own. Narrow it to the one
 * shape that carries a displayable message and fall back to the generic sentence for
 * anything else, including an `ApiError` that arrived without a wire message.
 */
function submitErrorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : genericSubmitError;
}

export function ContactDetailsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const esb = useEsb();
  const [submitError, setSubmitError] = useState<unknown>(null);
  const state = (location.state ?? readCheckoutDraft() ?? {}) as Partial<ContactRouteState>;
  const stored = readCheckoutDraft();
  const form = useForm<ContactValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: {
      fullName: stored?.contact?.fullName ?? '',
      email: stored?.contact?.email ?? user?.email ?? '',
      phone: stored?.contact?.phone ?? '',
    },
  });

  if (!state.eventId || !state.seatIds?.length) return <Navigate to="/events" replace />;

  const submit = async (values: ContactValues) => {
    setSubmitError(null);
    try {
      await esb.upsertCustomerProfile(values);
      const draft = writeCheckoutDraft({
        eventId: state.eventId as string,
        eventName: state.eventName,
        seatIds: state.seatIds as string[],
        contact: values,
      });
      navigate('/checkout', { state: draft });
    } catch (error) {
      setSubmitError(error);
    }
  };

  return (
    <section className="container page-section">
      <Link to={`/events/${encodeURIComponent(state.eventId)}/seats`} className="back-link">
        ← Change selection
      </Link>
      <div className="detail-layout">
        <form className="detail-main checkout-stack" onSubmit={form.handleSubmit(submit)} noValidate>
          <p className="eyebrow">Step 2 of 3</p>
          <h1>Customer contact details</h1>
          <p className="lede">
            The ESB forwards this profile to Customer Service. Customer Service remains authoritative
            for normalization, uniqueness, consent and the Identity-to-Customer mapping.
          </p>

          <Card padded className="contact-form-card">
            <FormField
              label="Full name"
              htmlFor="checkout-full-name"
              required
              error={form.formState.errors.fullName?.message}
            >
              <Input
                {...form.register('fullName')}
                id="checkout-full-name"
                autoComplete="name"
                placeholder="Nguyen Van A"
              />
            </FormField>
            <FormField
              label="Email"
              htmlFor="checkout-email"
              required
              error={form.formState.errors.email?.message}
            >
              <Input
                {...form.register('email')}
                id="checkout-email"
                type="email"
                autoComplete="email"
                placeholder="customer@example.com"
              />
            </FormField>
            <FormField
              label="Phone"
              htmlFor="checkout-phone"
              required
              error={form.formState.errors.phone?.message}
            >
              <Input
                {...form.register('phone')}
                id="checkout-phone"
                type="tel"
                autoComplete="tel"
                placeholder="+84 901 234 567"
              />
            </FormField>
          </Card>

          {submitError != null && (
            <Alert tone="danger" title="Customer profile could not be saved">
              {submitErrorMessage(submitError)}
              <ApiErrorDetails error={submitError} />
            </Alert>
          )}

          <Button type="submit" fullWidth disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? 'Saving profile…' : 'Continue to payment'}
            {!form.formState.isSubmitting && <ArrowRight size={17} />}
          </Button>
        </form>

        <Card padded className="booking-panel">
          <h2>{state.eventName ?? state.eventId}</h2>
          <dl className="facts">
            <div>
              <dt>
                <UserRound size={16} /> Customer
              </dt>
              <dd>{form.watch('fullName') || 'Not entered'}</dd>
            </div>
            <div>
              <dt>
                <Mail size={16} /> Email
              </dt>
              <dd>{form.watch('email') || 'Not entered'}</dd>
            </div>
            <div>
              <dt>
                <Phone size={16} /> Phone
              </dt>
              <dd>{form.watch('phone') || 'Not entered'}</dd>
            </div>
            <div>
              <dt>Seats</dt>
              <dd>{state.seatIds.join(', ')}</dd>
            </div>
          </dl>
        </Card>
      </div>
    </section>
  );
}
