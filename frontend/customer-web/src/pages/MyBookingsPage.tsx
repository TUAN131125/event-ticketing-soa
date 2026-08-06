import { useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { RefreshCw, Search, Ticket } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Pagination,
  Spinner,
} from '@event-ticketing/shared-ui';
import { useBookings } from '../app/hooks';
import { describeBookingStatus } from '../domain/booking-status';
import { QueryState } from './PageState';

export function MyBookingsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [bookingId, setBookingId] = useState('');
  const page = Math.max(1, Number(params.get('page') ?? 1));
  const bookings = useBookings(page);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (bookingId.trim()) navigate(`/bookings/${encodeURIComponent(bookingId.trim())}`);
  };

  return (
    <section className="container page-section">
      <div className="page-heading split-heading">
        <div>
          <p className="eyebrow">Authoritative booking history</p>
          <h1>My bookings</h1>
          <p className="lede">
            Booking status is always reloaded from the ESB. A recent-ID fallback is used only until
            the owner-scoped list route is added to the public contract.
          </p>
        </div>
        <Button
          variant="secondary"
          disabled={bookings.isFetching}
          onClick={() => void bookings.refetch()}
        >
          <RefreshCw size={17} /> {bookings.isFetching ? 'Refreshing…' : 'Refresh'}
        </Button>
      </div>

      <Card padded>
        <form className="search-bar" onSubmit={submit}>
          <Search size={18} />
          <Input
            aria-label="Booking ID"
            placeholder="BKG-..."
            value={bookingId}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setBookingId(event.target.value)}
          />
          <Button type="submit">Look up</Button>
        </form>
      </Card>

      {bookings.data?.source === 'recent-index' && (
        <Alert tone="info" title="Owner-scoped booking list is awaiting the ESB facade">
          The cards below are still authoritative reads, but the browser found them through its
          recent booking-ID index rather than a backend history query.
        </Alert>
      )}

      {bookings.isLoading && (
        <div className="page-state compact-state">
          <Spinner label="Loading bookings" />
        </div>
      )}

      {bookings.isError && (
        <QueryState error={bookings.error} retry={() => void bookings.refetch()} />
      )}

      {(bookings.data?.items ?? []).length ? (
        <>
          <div className="booking-history-grid">
            {(bookings.data?.items ?? []).map((booking) => {
              const view = describeBookingStatus(booking.status);
              return (
                <Card padded key={booking.bookingId} className="booking-history-card">
                  <div className="booking-history-card__header">
                    <span className="wallet-ticket__icon">
                      <Ticket size={21} />
                    </span>
                    <Badge tone={view.tone}>{view.label}</Badge>
                  </div>
                  <h2>{booking.bookingId}</h2>
                  <p className="muted">{view.description}</p>
                  <dl className="facts compact-facts">
                    <div>
                      <dt>Total</dt>
                      <dd>
                        {booking.total.amountMinor.toLocaleString()} {booking.total.currency}
                      </dd>
                    </div>
                    {booking.eventId && (
                      <div>
                        <dt>Event</dt>
                        <dd>{booking.eventId}</dd>
                      </div>
                    )}
                    <div>
                      <dt>Tickets</dt>
                      <dd>{booking.ticketIds?.length ?? 0}</dd>
                    </div>
                  </dl>
                  <Link
                    className="button button-secondary"
                    to={`/bookings/${encodeURIComponent(booking.bookingId)}`}
                  >
                    View booking
                  </Link>
                </Card>
              );
            })}
          </div>
          {bookings.data?.source === 'owner-list' && (
            <Pagination
              page={page}
              pageCount={Math.max(1, Math.ceil(bookings.data.total / 20))}
              onPageChange={(nextPage: number) => {
                setParams({ page: String(nextPage) });
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
            />
          )}
        </>
      ) : (
        !bookings.isLoading &&
        !bookings.isError && (
          <EmptyState
            title="No bookings found"
            description="Create a booking or paste an existing booking ID above."
            action={
              <Link to="/events" className="button button-primary">
                Browse events
              </Link>
            }
          />
        )
      )}
    </section>
  );
}
