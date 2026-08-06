import { useState, type ChangeEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Badge,
  Button,
  Card,
  ConfirmationDialog,
  Spinner,
  Textarea,
} from '@event-ticketing/shared-ui';
import { useBooking, useCancelBooking } from '../app/hooks';
import { ApiError } from '../api/auth-client';
import { ApiErrorDetails } from '../components/common/ApiErrorDetails';
import { describeBookingStatus, isConfirmed } from '../domain/booking-status';
import { QueryState } from './PageState';

const CANCELLATION_BLOCKED = new Set([
  'FAILED',
  'CANCELLED',
  'COMPENSATION_PENDING',
  'PAYMENT_PROCESSING',
]);

export function BookingDetailPage() {
  const { bookingId = '' } = useParams();
  const booking = useBooking(bookingId);
  const cancel = useCancelBooking(bookingId);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [reason, setReason] = useState('Customer requested cancellation');

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
  const cancellationBlocked = CANCELLATION_BLOCKED.has(value.status);
  const cancelError = cancel.error instanceof ApiError ? cancel.error : null;

  return (
    <section className="container page-section">
      <Link to="/bookings" className="back-link">
        ← My bookings
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
              {Boolean(value.seatIds?.length) && (
                <div>
                  <dt>Seat IDs</dt>
                  <dd>{value.seatIds?.join(', ')}</dd>
                </div>
              )}
            </dl>
          </Card>
          {cancel.isError && (
            <div className="notice notice-danger" role="alert">
              <div>
                <strong>{cancelError?.message ?? 'Cancellation failed.'}</strong>
                <ApiErrorDetails error={cancel.error} />
              </div>
            </div>
          )}
        </div>

        <Card padded className="booking-panel">
          <h2>Actions</h2>
          <Button
            fullWidth
            variant="secondary"
            disabled={cancel.isPending || cancellationBlocked}
            onClick={() => setConfirmOpen(true)}
          >
            Cancel booking
          </Button>
          {cancellationBlocked && (
            <p className="muted">
              Cancellation is unavailable while payment or compensation is running, or after the
              booking has already failed/cancelled. The server remains authoritative for policy.
            </p>
          )}
          {confirmed &&
            value.ticketIds?.map((ticketId) => (
              <Link
                key={ticketId}
                className="button button-ghost"
                to={`/tickets/${encodeURIComponent(ticketId)}`}
              >
                Ticket {ticketId}
              </Link>
            ))}
        </Card>
      </div>

      <ConfirmationDialog
        open={confirmOpen}
        title="Cancel this booking?"
        onClose={() => setConfirmOpen(false)}
        onConfirm={() =>
          cancel.mutate(
            { reason: reason.trim() || 'Customer requested cancellation' },
            { onSuccess: () => setConfirmOpen(false) },
          )
        }
        confirmLabel="Confirm cancellation"
        tone="danger"
        loading={cancel.isPending}
      >
        <p>
          The ESB may need to release seats and refund a captured demo payment. The final result
          comes from the authoritative booking workflow.
        </p>
        <label htmlFor="cancel-reason">
          <strong>Reason</strong>
        </label>
        <Textarea
          id="cancel-reason"
          value={reason}
          maxLength={250}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setReason(event.target.value)}
        />
      </ConfirmationDialog>
    </section>
  );
}
