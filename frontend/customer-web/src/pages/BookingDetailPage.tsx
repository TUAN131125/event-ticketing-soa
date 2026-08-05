import { Link, useParams } from 'react-router-dom';
import { CalendarDays, MapPin, Ticket } from 'lucide-react';
import { Badge, Card, Spinner } from '@event-ticketing/shared-ui';
import { useBooking } from '../app/hooks';
import { QueryState } from './PageState';
export function BookingDetailPage() {
  const { bookingId } = useParams();
  const result = useBooking(bookingId);
  if (result.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading booking" />
      </section>
    );
  if (result.isError || !result.data)
    return <QueryState error={result.error} retry={() => void result.refetch()} />;
  const booking = result.data;
  return (
    <section className="container page-section narrow-page">
      <Link to="/bookings" className="back-link">
        ← My bookings
      </Link>
      <Card>
        <div className="booking-row-head">
          <div>
            <p className="eyebrow">Booking</p>
            <h1>{booking.event?.name || booking.bookingId}</h1>
          </div>
          <Badge tone={booking.status === 'CONFIRMED' ? 'success' : 'warning'}>
            {booking.status}
          </Badge>
        </div>
        <dl className="facts">
          <div>
            <dt>
              <CalendarDays size={16} /> Date
            </dt>
            <dd>
              {booking.event?.startsAt ? new Date(booking.event.startsAt).toLocaleString() : '—'}
            </dd>
          </div>
          <div>
            <dt>
              <MapPin size={16} /> Venue
            </dt>
            <dd>{booking.event?.venue || '—'}</dd>
          </div>
          <div>
            <dt>Seats</dt>
            <dd>{booking.seats?.join(', ') || 'See ticket details'}</dd>
          </div>
        </dl>
        {booking.ticketIds?.length ? (
          <div className="ticket-links">
            {booking.ticketIds.map((ticketId) => (
              <Link key={ticketId} to={`/tickets/${ticketId}`} className="button button-secondary">
                <Ticket size={16} /> Ticket {ticketId}
              </Link>
            ))}
          </div>
        ) : (
          <p className="muted">Tickets will appear once payment is confirmed.</p>
        )}
        <Link to={`/bookings/${booking.bookingId}/status`} className="button button-ghost">
          View live status
        </Link>
      </Card>
    </section>
  );
}
