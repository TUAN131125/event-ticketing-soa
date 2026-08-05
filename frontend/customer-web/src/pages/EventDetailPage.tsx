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
            {event.imageUrl ? <img src={event.imageUrl} alt="" /> : <Ticket size={54} />}
          </div>
          <div className="event-card-meta">
            <Badge tone="information">{event.category || 'Live event'}</Badge>
            {event.status && <Badge>{event.status}</Badge>}
          </div>
          <h1>{event.name}</h1>
          <p className="lede">
            {event.description || 'Event details will be published by the organiser.'}
          </p>
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
              <dd>Live inventory</dd>
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
