import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Clock3, Loader2, Ticket, TriangleAlert } from 'lucide-react';
import { Badge, Card, Spinner } from '@event-ticketing/shared-ui';
import { useBooking, useEsb } from '../app/hooks';
import {
  BookingStatusSocket,
  statusSocketUrl,
  type AuthenticationFailureCode,
  type SocketState,
  type StatusEvent,
} from '../api/websocket-client';
import { describeBookingStatus, isConfirmed, isUnsuccessful } from '../domain/booking-status';
import { QueryState } from './PageState';

type ResultRouteState = { reconciling?: boolean; retryAfterSeconds?: number | null };

export function BookingResultPage() {
  const { bookingId } = useParams();
  const [params] = useSearchParams();
  const location = useLocation();
  const routeState = (location.state ?? {}) as ResultRouteState;
  const esb = useEsb();
  const result = useBooking(bookingId, routeState.retryAfterSeconds);
  const [liveState, setLiveState] = useState<SocketState>('connecting');
  const [liveEvent, setLiveEvent] = useState<StatusEvent | null>(null);
  const [liveRejected, setLiveRejected] = useState<AuthenticationFailureCode | null>(null);

  const { refetch } = result;
  // The stream is a projection only. Any connect or resync signal reloads the
  // authoritative booking from `GET /api/bookings/{bookingId}`.
  const reloadAuthoritative = useCallback(() => void refetch(), [refetch]);

  useEffect(() => {
    const currentBookingId = bookingId;
    const url = currentBookingId ? statusSocketUrl(currentBookingId) : '';
    if (!url || !currentBookingId) {
      setLiveState('closed');
      return undefined;
    }
    setLiveRejected(null);
    const socket = new BookingStatusSocket(url, currentBookingId, {
      ticketProvider: () => esb.issueRealtimeWsTicket(currentBookingId),
    });
    return socket.connect({
      onMessage: setLiveEvent,
      onState: setLiveState,
      onResync: reloadAuthoritative,
      onAuthenticationFailed: setLiveRejected,
    });
  }, [bookingId, esb, reloadAuthoritative]);

  if (result.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading booking status" />
      </section>
    );
  if (result.isError || !result.data)
    return <QueryState error={result.error} retry={() => void result.refetch()} />;

  const booking = result.data;
  // REST is authoritative; the live projection is only used for the progress note.
  const view = describeBookingStatus(booking.status);
  const confirmed = isConfirmed(booking.status);
  const unsuccessful = isUnsuccessful(booking.status);
  const reconciling = Boolean(routeState.reconciling) && view.inProgress;

  return (
    <section className="container page-section narrow-page">
      <Card className="result-card">
        <div className="result-icon">
          {confirmed ? (
            <CheckCircle2 size={34} />
          ) : unsuccessful ? (
            <TriangleAlert size={34} />
          ) : (
            <Loader2 size={34} />
          )}
        </div>
        <p className="eyebrow">{params.get('created') ? 'Booking received' : 'Booking status'}</p>
        <h1>
          {confirmed
            ? 'You are all set'
            : unsuccessful
              ? 'This booking did not complete'
              : 'Your booking is being processed'}
        </h1>
        <p className="lede">
          Booking <strong>{booking.bookingId}</strong> has status{' '}
          <Badge tone={view.tone}>{view.label}</Badge>.
        </p>
        <p className="muted">{view.description}</p>
        {reconciling && (
          <p className="muted">
            The ESB accepted the request and is reconciling the payment outcome. This page keeps
            reloading the authoritative status; do not place the booking again.
          </p>
        )}
        {liveState === 'open' ? (
          <p className="live-note">
            <span className="live-dot" /> Live updates connected
            {liveEvent?.message ? ` — ${liveEvent.message}` : ''}
          </p>
        ) : (
          <p className="live-note">
            <Clock3 size={16} />{' '}
            {liveRejected
              ? 'Live updates were declined for this booking; the status below is still authoritative.'
              : 'Live updates are unavailable; this page refreshes automatically.'}
          </p>
        )}
        <div className="result-actions">
          <Link
            to={`/bookings/${encodeURIComponent(booking.bookingId)}`}
            className="button button-primary"
          >
            <Ticket size={17} /> View booking
          </Link>
          <Link to="/events" className="button button-secondary">
            Browse more events
          </Link>
        </div>
      </Card>
    </section>
  );
}
