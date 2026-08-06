import { Link, useParams } from 'react-router-dom';
import { CalendarDays, MapPin, QrCode, ShieldCheck, Ticket } from 'lucide-react';
import { Alert, Badge, Card, Spinner } from '@event-ticketing/shared-ui';
import { useTicket } from '../app/hooks';
import { QueryState } from './PageState';

function formatDate(value?: string | null) {
  if (!value) return 'Not published';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export function TicketDetailPage() {
  const { ticketId = '' } = useParams();
  const ticket = useTicket(ticketId);

  if (ticket.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading ticket" />
      </section>
    );

  if (ticket.isError || !ticket.data) {
    return (
      <QueryState
        error={ticket.error}
        retry={() => void ticket.refetch()}
        notFound={!ticket.data}
        serviceName="ticket facade"
      />
    );
  }

  const value = ticket.data;
  return (
    <section className="container page-section">
      <Link to="/tickets" className="back-link">
        ← Ticket wallet
      </Link>
      <div className="ticket-detail-layout">
        <Card padded className="ticket-card digital-ticket-card">
          <div className="digital-ticket-card__topline">
            <span className="wallet-ticket__icon">
              <Ticket size={24} />
            </span>
            <Badge
              tone={
                value.status === 'ISSUED'
                  ? 'success'
                  : value.status === 'CHECKED_IN'
                    ? 'information'
                    : 'danger'
              }
            >
              {value.status}
            </Badge>
          </div>
          <p className="eyebrow">Electronic ticket</p>
          <h1>{value.eventName ?? value.ticketId}</h1>

          <div className="qr-projection" aria-label="Ticket QR projection">
            {value.qrToken ? (
              <>
                <QrCode size={72} />
                <code>{value.qrToken}</code>
              </>
            ) : (
              <>
                <QrCode size={72} />
                <span>QR projection unavailable</span>
              </>
            )}
          </div>

          <dl className="facts ticket-facts">
            <div>
              <dt>Ticket</dt>
              <dd>{value.ticketId}</dd>
            </div>
            <div>
              <dt>
                <CalendarDays size={16} /> Date
              </dt>
              <dd>{formatDate(value.startsAt)}</dd>
            </div>
            <div>
              <dt>
                <MapPin size={16} /> Venue
              </dt>
              <dd>{value.venue ?? 'Not published'}</dd>
            </div>
            <div>
              <dt>Seat</dt>
              <dd>{value.seatCode ?? value.seatId ?? 'General admission'}</dd>
            </div>
            <div>
              <dt>Booking</dt>
              <dd>{value.bookingId}</dd>
            </div>
          </dl>
        </Card>

        <div className="ticket-detail-aside">
          {value.status === 'CHECKED_IN' && (
            <Alert tone="info" title="Already checked in">
              Ticket Service reports that this ticket has already been used for entry.
            </Alert>
          )}
          {value.status === 'CANCELLED' && (
            <Alert tone="danger" title="Ticket cancelled">
              This ticket is not valid for entry.
            </Alert>
          )}
          <Card padded>
            <h2>Entry guidance</h2>
            <p className="muted">
              <ShieldCheck size={16} /> Ticket validation and duplicate check-in prevention remain
              authoritative in Ticket Service.
            </p>
            {value.correlationId && (
              <p className="muted">Correlation ID: {value.correlationId}</p>
            )}
          </Card>
        </div>
      </div>
    </section>
  );
}
