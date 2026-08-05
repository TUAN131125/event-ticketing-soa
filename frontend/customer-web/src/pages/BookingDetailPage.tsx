import { Link, useParams } from 'react-router-dom';
import { Badge, Button, Card, Spinner } from '@event-ticketing/shared-ui';
import { useBooking, useCancelBooking } from '../app/hooks';
import { ApiError } from '../api/auth-client';
import { describeBookingStatus, isConfirmed, isSettled } from '../domain/booking-status';
import { QueryState } from './PageState';

export function BookingDetailPage() {
  const { bookingId = '' } = useParams();
  const booking = useBooking(bookingId);
  const cancel = useCancelBooking(bookingId);
  if (booking.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading booking" />
      </section>
    );
  if (booking.isError || !booking.data)
    return (
      <QueryState
        error={booking.error}
        retry={() => void booking.refetch()}
        notFound={!booking.data}
      />
    );
  const value = booking.data;
  const view = describeBookingStatus(value.status);
  const confirmed = isConfirmed(value.status);
  return (
    <section className="container page-section">
      <Link to="/bookings" className="back-link">
        ← Booking lookup
      </Link>
      <div className="detail-layout">
        <div className="detail-main">
          <p className="eyebrow">Booking</p>
          <h1>{value.bookingId}</h1>
          <Badge tone={view.tone}>{view.label}</Badge>
          <p className="muted">{view.description}</p>
          <Card padded>
            <dl className="facts">
              <div>
                <dt>Total</dt>
                <dd>
                  {value.total.amountMinor.toLocaleString()} {value.total.currency}
                </dd>
              </div>
              <div>
                <dt>Reservation</dt>
                <dd>{value.reservationId ?? '—'}</dd>
              </div>
              <div>
                <dt>Payment</dt>
                <dd>{value.paymentId ?? '—'}</dd>
              </div>
              <div>
                <dt>Correlation ID</dt>
                <dd>{value.correlationId}</dd>
              </div>
              {value.eventId && (
                <div>
                  <dt>Event</dt>
                  <dd>{value.eventId}</dd>
                </div>
              )}
              {value.seatIds?.length && (
                <div>
                  <dt>Seat IDs</dt>
                  <dd>{value.seatIds.join(', ')}</dd>
                </div>
              )}
            </dl>
          </Card>
          {cancel.isError && (
            <p className="form-error" role="alert">
              {cancel.error instanceof ApiError ? cancel.error.message : 'Cancellation failed.'}
            </p>
          )}
        </div>
        <Card padded className="booking-panel">
          <h2>Actions</h2>
          <Button
            fullWidth
            variant="secondary"
            disabled={cancel.isPending || isSettled(value.status)}
            onClick={() => cancel.mutate()}
          >
            {cancel.isPending ? 'Cancelling…' : 'Cancel booking'}
          </Button>
          {view.inProgress && (
            <p className="muted">
              Cancellation is unavailable while the workflow is still running. This page reloads the
              authoritative status on its own.
            </p>
          )}
          {confirmed &&
            value.ticketIds?.map((ticketId) => (
              <Link
                key={ticketId}
                className="button button-ghost"
                to={`/tickets/${encodeURIComponent(ticketId)}?bookingId=${encodeURIComponent(value.bookingId)}`}
              >
                Ticket {ticketId}
              </Link>
            ))}
        </Card>
      </div>
    </section>
  );
}
