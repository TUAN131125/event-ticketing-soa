import { useRef, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { CreditCard, ShieldCheck, UserRoundCheck } from 'lucide-react';
import { Alert, Button, Card, Radio } from '@event-ticketing/shared-ui';
import { useAuth } from '../app/auth';
import { useCreateBooking } from '../app/hooks';
import { ApiError } from '../api/auth-client';
import { ApiErrorDetails } from '../components/common/ApiErrorDetails';
import {
  clearCheckoutDraft,
  readCheckoutDraft,
  type CheckoutDraft,
} from '../utils/checkout-draft';

const PAYMENT_OPTIONS = [
  {
    token: 'tok_demo_success',
    label: 'Successful payment',
    description: 'The mock provider authorizes and captures the payment.',
  },
  {
    token: 'tok_demo_decline',
    label: 'Declined payment',
    description: 'The mock provider declines the payment and the ESB compensates the seat hold.',
  },
  {
    token: 'tok_demo_timeout',
    label: 'Timeout / reconciliation',
    description: 'The outcome is unknown and the ESB returns 202 while reconciliation continues.',
  },
] as const;

export function CheckoutPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const routeDraft = location.state as CheckoutDraft | null;
  const draft = routeDraft?.eventId ? routeDraft : readCheckoutDraft();
  const booking = useCreateBooking();
  const idempotency = useRef<{ fingerprint: string; key: string } | null>(null);

  if (!draft?.eventId || !draft.seatIds.length || !draft.contact)
    return <Navigate to="/events" replace />;

  const apiError = booking.error instanceof ApiError ? booking.error : null;
  const mappingMissing = apiError?.code === 'IDENTITY_NOT_MAPPED';

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const paymentMethodToken = String(form.get('paymentMethodToken') ?? 'tok_demo_success');
    const fingerprint = JSON.stringify({
      eventId: draft.eventId,
      seatIds: draft.seatIds,
      paymentMethodToken,
    });
    if (!idempotency.current || idempotency.current.fingerprint !== fingerprint) {
      idempotency.current = { fingerprint, key: crypto.randomUUID() };
    }

    booking.mutate(
      {
        idempotencyKey: idempotency.current.key,
        payload: {
          eventId: draft.eventId,
          seatIds: draft.seatIds,
          paymentMethodToken,
        },
      },
      {
        onSuccess: (submission) => {
          clearCheckoutDraft();
          navigate(`/bookings/${encodeURIComponent(submission.booking.bookingId)}/status`, {
            replace: true,
            state: {
              reconciling: submission.reconciling,
              retryAfterSeconds: submission.retryAfterSeconds,
            },
          });
        },
      },
    );
  };

  return (
    <section className="container page-section">
      <Link to="/checkout/contact" state={draft} className="back-link">
        ← Edit customer details
      </Link>
      <div className="detail-layout">
        <form className="detail-main checkout-stack" onSubmit={submit}>
          <p className="eyebrow">Step 3 of 3</p>
          <h1>Confirm your booking</h1>
          <p className="lede">Signed in as {user?.email}</p>

          <Card padded className="identity-confirmation-card">
            <UserRoundCheck size={24} />
            <div>
              <h2>Validated customer draft</h2>
              <p className="muted">
                {draft.contact.fullName} · {draft.contact.email} · {draft.contact.phone}
              </p>
              <p className="muted">
                The ESB resolves the authoritative Customer mapping from the signed-in identity.
              </p>
            </div>
          </Card>

          <Card padded>
            <fieldset className="payment-options">
              <legend>Demo payment outcome</legend>
              {PAYMENT_OPTIONS.map((option, index) => (
                <label className="payment-option" key={option.token}>
                  <Radio
                    name="paymentMethodToken"
                    value={option.token}
                    defaultChecked={index === 0}
                    disabled={booking.isPending}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <small>{option.description}</small>
                  </span>
                </label>
              ))}
            </fieldset>
            <p className="muted">Never enter real card or bank data in this demo.</p>
          </Card>

          {mappingMissing && (
            <Alert tone="warning" title="Customer identity is not mapped">
              This Identity account is not linked to an authoritative Customer profile. Return to the
              contact step and save the customer profile before placing the booking.
              <ApiErrorDetails error={booking.error} />
            </Alert>
          )}

          {booking.isError && !mappingMissing && (
            <Alert tone="danger" title="Booking could not be created">
              {apiError?.message ?? 'The booking request could not be completed.'}
              <ApiErrorDetails error={booking.error} />
            </Alert>
          )}

          <Button type="submit" disabled={booking.isPending} fullWidth>
            <CreditCard size={17} /> {booking.isPending ? 'Processing…' : 'Place booking'}
          </Button>
        </form>

        <Card padded className="booking-panel">
          <h2>{draft.eventName ?? draft.eventId}</h2>
          <dl className="facts">
            <div>
              <dt>Event</dt>
              <dd>{draft.eventId}</dd>
            </div>
            <div>
              <dt>Seats</dt>
              <dd>{draft.seatIds.join(', ')}</dd>
            </div>
            <div>
              <dt>Customer</dt>
              <dd>{draft.contact.fullName}</dd>
            </div>
          </dl>
          <p className="muted">
            <ShieldCheck size={16} /> Final amount, availability and payment status come only from
            authoritative backend services.
          </p>
        </Card>
      </div>
    </section>
  );
}
