import { Link } from 'react-router-dom';
import { CalendarDays, Ticket } from 'lucide-react';
import { Badge, Card, EmptyState, Skeleton } from '@event-ticketing/shared-ui';
import { useBookings } from '../app/hooks';
import { QueryState } from './PageState';
function formatDate(value?: string) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
}
export function MyBookingsPage() {
  const result = useBookings(true);
  if (result.isLoading)
    return (
      <section className="container page-section">
        <div className="stack-list">
          <Skeleton height={86} />
          <Skeleton height={86} />
        </div>
      </section>
    );
  if (result.isError)
    return <QueryState error={result.error} retry={() => void result.refetch()} />;
  if (!result.data?.items.length)
    return (
      <section className="container page-section">
        <EmptyState
          title="No bookings yet"
          description="Your confirmed tickets will appear here after you book an event."
          action={
            <Link to="/events" className="button button-primary">
              Browse events
            </Link>
          }
        />
      </section>
    );
  return (
    <section className="container page-section">
      <div className="page-heading">
        <p className="eyebrow">Your plans</p>
        <h1>My bookings</h1>
        <p className="lede">Keep every ticket and booking status in one place.</p>
      </div>
      <div className="stack-list">
        {result.data.items.map((booking) => (
          <Card key={booking.bookingId} className="booking-row">
            <div className="booking-row-icon">
              <Ticket size={20} />
            </div>
            <div className="booking-row-content">
              <div className="booking-row-head">
                <h2>
                  <Link to={`/bookings/${booking.bookingId}`}>
                    {booking.event?.name || `Booking ${booking.bookingId}`}
                  </Link>
                </h2>
                <Badge
                  tone={
                    booking.status === 'CONFIRMED'
                      ? 'success'
                      : booking.status === 'CANCELLED'
                        ? 'danger'
                        : 'warning'
                  }
                >
                  {booking.status}
                </Badge>
              </div>
              <p>
                <CalendarDays size={15} />{' '}
                {formatDate(booking.event?.startsAt ?? booking.createdAt)}{' '}
                {booking.event?.venue ? ` · ${booking.event.venue}` : ''}
              </p>
            </div>
            <Link to={`/bookings/${booking.bookingId}`} className="button button-secondary">
              View
            </Link>
          </Card>
        ))}
      </div>
    </section>
  );
}
