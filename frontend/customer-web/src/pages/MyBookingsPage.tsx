import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, Ticket } from 'lucide-react';
import { Button, Card, EmptyState, Input } from '@event-ticketing/shared-ui';
import { recentBookingIds } from '../api/esb-client';

export function MyBookingsPage() {
  const navigate = useNavigate();
  const [bookingId, setBookingId] = useState('');
  const ids = recentBookingIds();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (bookingId.trim()) navigate(`/bookings/${encodeURIComponent(bookingId.trim())}`);
  };
  return (
    <section className="container page-section">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Authoritative lookup</p>
          <h1>My bookings</h1>
          <p className="lede">
            The ESB currently exposes lookup by bookingId, not a booking-list operation. IDs below
            are only recent browser history; each detail page reloads authoritative state from the
            ESB.
          </p>
        </div>
      </div>
      <Card padded>
        <form className="search-bar" onSubmit={submit}>
          <Search size={18} />
          <Input
            aria-label="Booking ID"
            placeholder="BKG-..."
            value={bookingId}
            onChange={(event) => setBookingId(event.target.value)}
          />
          <Button type="submit">Look up</Button>
        </form>
      </Card>
      {ids.length ? (
        <div className="event-grid">
          {ids.map((id) => (
            <Card padded key={id}>
              <Ticket size={22} />
              <h2>{id}</h2>
              <Link className="button button-secondary" to={`/bookings/${encodeURIComponent(id)}`}>
                View current status
              </Link>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No recent booking IDs"
          description="Create a booking or paste an existing booking ID above."
          action={
            <Link to="/events" className="button button-primary">
              Browse events
            </Link>
          }
        />
      )}
    </section>
  );
}
