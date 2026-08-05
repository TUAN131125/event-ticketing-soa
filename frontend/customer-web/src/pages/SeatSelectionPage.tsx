import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowRight, Info, Ticket } from 'lucide-react';
import { Badge, Button, Card, Input, Spinner } from '@event-ticketing/shared-ui';
import { useEvent } from '../app/hooks';
import { QueryState } from './PageState';

function splitSeatIds(value: string): string[] {
  return [
    ...new Set(
      value
        .split(/[\s,;]+/)
        .map((seat) => seat.trim())
        .filter(Boolean),
    ),
  ].slice(0, 10);
}

export function SeatSelectionPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const event = useEvent(eventId);
  const [seatText, setSeatText] = useState('A01');
  const seatIds = useMemo(() => splitSeatIds(seatText), [seatText]);

  if (event.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading event" />
      </section>
    );
  if (event.isError || !event.data)
    return (
      <QueryState
        error={event.error}
        retry={() => void event.refetch()}
        notFound={!event.data}
        serviceName="event service"
      />
    );

  return (
    <section className="container page-section">
      <Link to={`/events/${encodeURIComponent(event.data.eventId)}`} className="back-link">
        ← {event.data.name}
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Step 1 of 2</p>
          <h1>Choose ticket or seat references</h1>
          <p className="lede">
            The current ESB contract accepts up to 10 <code>seatIds</code>. Seat-map browsing is not
            published by the public ESB API yet, so this restored UI uses explicit seat references.
          </p>
        </div>
      </div>

      {event.data.ticketTypes.length > 0 && (
        <div className="event-grid">
          {event.data.ticketTypes.map((ticketType, index) => (
            <Card padded key={ticketType.ticketTypeId ?? index}>
              <div className="event-card-meta">
                <Badge tone="information">Ticket type</Badge>
              </div>
              <h2>{ticketType.name ?? `Option ${index + 1}`}</h2>
              {ticketType.price && (
                <p>
                  {ticketType.price.amountMinor.toLocaleString()} {ticketType.price.currency}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}

      <div className="detail-layout">
        <Card padded className="detail-main">
          <label htmlFor="seat-ids">
            <strong>Seat IDs</strong>
          </label>
          <Input
            id="seat-ids"
            value={seatText}
            onChange={(inputEvent) => setSeatText(inputEvent.target.value)}
            placeholder="A01, A02"
            aria-describedby="seat-help"
          />
          <p id="seat-help" className="muted">
            Separate values with commas or spaces. Availability is validated authoritatively by Seat
            Inventory through the ESB when the booking is submitted.
          </p>
          <div className="event-card-meta">
            {seatIds.map((seatId) => (
              <Badge key={seatId}>{seatId}</Badge>
            ))}
          </div>
        </Card>
        <Card padded className="booking-panel">
          <h2>Selection summary</h2>
          <p>
            <Ticket size={16} /> {seatIds.length} reference{seatIds.length === 1 ? '' : 's'}
          </p>
          <div className="notice notice-information">
            <Info size={18} />
            <span>
              The UI never decides that a seat is available; the backend remains authoritative.
            </span>
          </div>
          <Button
            fullWidth
            disabled={seatIds.length === 0}
            onClick={() =>
              navigate('/checkout', {
                state: {
                  eventId: event.data.eventId,
                  eventName: event.data.name,
                  seatIds,
                },
              })
            }
          >
            Continue to checkout <ArrowRight size={17} />
          </Button>
        </Card>
      </div>
    </section>
  );
}
