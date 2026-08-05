import { useMemo, useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { CreditCard, ShieldCheck } from 'lucide-react';
import { Button, Card, Input } from '@event-ticketing/shared-ui';
import { useAuth } from '../app/auth';
import { useCreateBooking } from '../app/hooks';
import { ApiError } from '../api/auth-client';

type CheckoutState = { eventId?: string; eventName?: string; seatIds?: string[] };

export function CheckoutPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const state = (location.state ?? {}) as CheckoutState;
  const booking = useCreateBooking();
  const [customerId, setCustomerId] = useState(
    () => localStorage.getItem('evently.customerId') ?? '',
  );
  const [paymentMethodToken, setPaymentMethodToken] = useState('tok_demo_success');
  const idempotencyKey = useMemo(
    () => crypto.randomUUID(),
    [state.eventId, state.seatIds?.join('|')],
  );

  if (!state.eventId || !state.seatIds?.length) return <Navigate to="/events" replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    localStorage.setItem('evently.customerId', customerId.trim());
    booking.mutate(
      {
        idempotencyKey,
        payload: {
          customerId: customerId.trim(),
          eventId: state.eventId as string,
          seatIds: state.seatIds as string[],
          paymentMethodToken: paymentMethodToken.trim(),
        },
      },
      {
        // A 201 is a settled outcome and a 202 means the ESB is reconciling the payment.
        // Both land on the status screen, which polls the authoritative booking; the
        // command is never resubmitted from the browser.
        onSuccess: (submission) =>
          navigate(`/bookings/${encodeURIComponent(submission.booking.bookingId)}/status`, {
            replace: true,
            state: {
              reconciling: submission.reconciling,
              retryAfterSeconds: submission.retryAfterSeconds,
            },
          }),
      },
    );
  };

  return (
    <section className="container page-section">
      <Link to={`/events/${encodeURIComponent(state.eventId)}/seats`} className="back-link">
        ← Change selection
      </Link>
      <div className="detail-layout">
        <form className="detail-main" onSubmit={submit}>
          <p className="eyebrow">Step 2 of 2</p>
          <h1>Confirm your booking</h1>
          <p className="lede">Signed in as {user?.email}</p>
          <Card padded>
            <label htmlFor="customer-id">
              <strong>Customer ID</strong>
            </label>
            <Input
              id="customer-id"
              value={customerId}
              onChange={(inputEvent) => setCustomerId(inputEvent.target.value)}
              placeholder="CUST-DEMO-001"
              required
            />
            <p className="muted">
              Identity and Customer are separate domains, so this is not inferred from your userId.
              The public booking contract requires the field, but ownership is decided by the ESB
              from your signed-in identity, not by what is typed here.
            </p>
          </Card>
          <Card padded>
            <label htmlFor="payment-token">
              <strong>Demo payment token</strong>
            </label>
            <Input
              id="payment-token"
              value={paymentMethodToken}
              onChange={(inputEvent) => setPaymentMethodToken(inputEvent.target.value)}
              minLength={6}
              required
            />
            <p className="muted">Use the configured demo token; never enter real card data.</p>
          </Card>
          {booking.isError && (
            <p className="form-error" role="alert">
              {booking.error instanceof ApiError
                ? booking.error.message
                : 'Booking could not be created.'}
            </p>
          )}
          <Button type="submit" disabled={booking.isPending}>
            <CreditCard size={17} /> {booking.isPending ? 'Processing…' : 'Place booking'}
          </Button>
        </form>
        <Card padded className="booking-panel">
          <h2>{state.eventName ?? state.eventId}</h2>
          <dl className="facts">
            <div>
              <dt>Event</dt>
              <dd>{state.eventId}</dd>
            </div>
            <div>
              <dt>Seat IDs</dt>
              <dd>{state.seatIds.join(', ')}</dd>
            </div>
          </dl>
          <p className="muted">
            <ShieldCheck size={16} /> Final amount and availability are calculated by authoritative
            services, not by the browser.
          </p>
        </Card>
      </div>
    </section>
  );
}
