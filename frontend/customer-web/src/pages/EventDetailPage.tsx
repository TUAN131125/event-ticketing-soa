import { Link, useNavigate, useParams } from 'react-router-dom';
import { CalendarDays, Clock3, MapPin, Share2, Ticket } from 'lucide-react';
import { Badge, Button, Card, Skeleton } from '@event-ticketing/shared-ui';
import { useEvent } from '../app/hooks';
import { QueryState } from './PageState';

function formatDate(value?: string) {
  if (!value) return 'Date to be announced';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'full', timeStyle: 'short' }).format(date);
}

function formatMoney(amountMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amountMinor);
}

export function EventDetailPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const result = useEvent(eventId);
  if (result.isLoading)
    return (
      <section className="container page-section">
        <Skeleton height={320} />
        <Skeleton width="60%" />
        <Skeleton width="80%" />
      </section>
    );
  if (result.isError || !result.data)
    return (
      <QueryState
        error={result.error}
        retry={() => void result.refetch()}
        notFound={!result.data && !result.error}
        serviceName="event service"
      />
    );
  const event = result.data;
  return (
    <section className="container page-section">
      <Link to="/events" className="back-link">
        ← All events
      </Link>
      <div className="detail-layout">
        <div className="detail-main">
          <div className="detail-cover">
            <Ticket size={54} />
          </div>
          <div className="event-card-meta">
            <Badge tone="information">{event.status || 'Status unavailable'}</Badge>
          </div>
          <h1>{event.name}</h1>
          <p className="lede">
            Review the published schedule, venue and ticket prices before choosing seats.
          </p>

          <section className="ticket-types-section" aria-labelledby="ticket-types-heading">
            <div className="section-toolbar">
              <h2 id="ticket-types-heading">Ticket types and published prices</h2>
            </div>
            {event.ticketTypes.length ? (
              <div className="ticket-type-list">
                {event.ticketTypes.map((ticketType, index) => (
                  <Card padded key={ticketType.ticketTypeId ?? index}>
                    <div>
                      <strong>{ticketType.name ?? `Ticket type ${index + 1}`}</strong>
                      <p className="muted">{ticketType.ticketTypeId ?? 'Type identifier pending'}</p>
                    </div>
                    <strong>
                      {ticketType.price
                        ? formatMoney(ticketType.price.amountMinor, ticketType.price.currency)
                        : 'Price from server at checkout'}
                    </strong>
                  </Card>
                ))}
              </div>
            ) : (
              <p className="muted">Ticket types have not been published yet.</p>
            )}
          </section>
        </div>
        <Card padded className="booking-panel">
          <h2>Ready to go?</h2>
          <dl className="facts">
            <div>
              <dt>
                <CalendarDays size={16} /> Date
              </dt>
              <dd>{formatDate(event.startsAt)}</dd>
            </div>
            <div>
              <dt>
                <MapPin size={16} /> Venue
              </dt>
              <dd>{event.venue || 'To be announced'}</dd>
            </div>
            <div>
              <dt>
                <Clock3 size={16} /> Availability
              </dt>
              <dd>Loaded on seat-selection screen</dd>
            </div>
          </dl>
          <Button fullWidth onClick={() => navigate(`/events/${event.eventId}/seats`)}>
            Choose seats <Ticket size={17} />
          </Button>
          <Button
            fullWidth
            variant="ghost"
            onClick={() => void navigator.clipboard?.writeText(window.location.href)}
          >
            <Share2 size={16} /> Share event
          </Button>
        </Card>
      </div>
    </section>
  );
}
