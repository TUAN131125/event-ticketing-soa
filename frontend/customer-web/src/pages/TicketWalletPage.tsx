import { Link, useSearchParams } from 'react-router-dom';
import { CalendarDays, QrCode, Ticket } from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Pagination,
  Spinner,
} from '@event-ticketing/shared-ui';
import { useTickets } from '../app/hooks';
import { ApiError } from '../api/auth-client';
import { ApiErrorDetails } from '../components/common/ApiErrorDetails';
import { QueryState } from './PageState';

export function TicketWalletPage() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get('page') ?? 1));
  const tickets = useTickets(page);
  const apiError = tickets.error instanceof ApiError ? tickets.error : null;
  const facadePending = apiError && [404, 405, 501].includes(apiError.status);

  if (tickets.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading tickets" />
      </section>
    );

  return (
    <section className="container page-section">
      <div className="page-heading split-heading">
        <div>
          <p className="eyebrow">Ticket wallet</p>
          <h1>Your electronic tickets</h1>
          <p className="lede">
            Every card is an owner-scoped Ticket Service projection delivered through the ESB.
          </p>
        </div>
        <Link className="button button-secondary" to="/bookings">
          View bookings
        </Link>
      </div>

      {tickets.isError ? (
        facadePending ? (
          <Card padded className="notice-card">
            <QrCode size={28} />
            <div>
              <h2>Ticket wallet is ready for the ESB ticket facade</h2>
              <p className="muted">
                Publish GET /api/tickets to populate this screen without the browser calling Ticket
                Service directly.
              </p>
              <ApiErrorDetails error={tickets.error} />
            </div>
            <Button variant="secondary" onClick={() => void tickets.refetch()}>
              Retry
            </Button>
          </Card>
        ) : (
          <QueryState error={tickets.error} retry={() => void tickets.refetch()} serviceName="ticket facade" />
        )
      ) : tickets.data?.items.length ? (
        <>
          <div className="ticket-wallet-grid">
            {tickets.data.items.map((ticket) => (
              <Card padded className="wallet-ticket" key={ticket.ticketId}>
                <div className="wallet-ticket__icon">
                  <Ticket size={24} />
                </div>
                <div className="event-card-meta">
                  <Badge
                    tone={
                      ticket.status === 'ISSUED'
                        ? 'success'
                        : ticket.status === 'CHECKED_IN'
                          ? 'information'
                          : 'danger'
                    }
                  >
                    {ticket.status}
                  </Badge>
                  <span>{ticket.ticketTypeName ?? 'Electronic ticket'}</span>
                </div>
                <h2>{ticket.eventName ?? ticket.ticketId}</h2>
                <dl className="facts compact-facts">
                  <div>
                    <dt>Ticket</dt>
                    <dd>{ticket.ticketId}</dd>
                  </div>
                  <div>
                    <dt>Booking</dt>
                    <dd>{ticket.bookingId}</dd>
                  </div>
                  {ticket.seatCode && (
                    <div>
                      <dt>Seat</dt>
                      <dd>{ticket.seatCode}</dd>
                    </div>
                  )}
                </dl>
                <div className="wallet-ticket__actions">
                  <Link
                    className="button button-primary"
                    to={`/tickets/${encodeURIComponent(ticket.ticketId)}`}
                  >
                    <QrCode size={17} /> Open ticket
                  </Link>
                  <Link
                    className="button button-ghost"
                    to={`/bookings/${encodeURIComponent(ticket.bookingId)}`}
                  >
                    Booking details
                  </Link>
                </div>
              </Card>
            ))}
          </div>
          <Pagination
            page={page}
            pageCount={Math.max(1, Math.ceil(tickets.data.totalItems / tickets.data.pageSize))}
            onPageChange={(nextPage: number) => setParams({ page: String(nextPage) })}
          />
        </>
      ) : (
        <EmptyState
          title="No tickets yet"
          description="Issued tickets appear here after a confirmed booking."
          action={
            <Link to="/events" className="button button-primary">
              <CalendarDays size={17} /> Browse events
            </Link>
          }
        />
      )}
    </section>
  );
}
