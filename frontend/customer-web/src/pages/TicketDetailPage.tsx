import { Link, useParams, useSearchParams } from 'react-router-dom';
import { QrCode, Ticket } from 'lucide-react';
import { Badge, Card, EmptyState } from '@event-ticketing/shared-ui';
import { useBooking } from '../app/hooks';

export function TicketDetailPage() {
  const { ticketId = '' } = useParams();
  const [params] = useSearchParams();
  const bookingId = params.get('bookingId') ?? undefined;
  const booking = useBooking(bookingId);
  if (!bookingId)
    return (
      <EmptyState
        title="Booking reference required"
        description="The current public ESB contract returns ticket IDs inside BookingResult but does not publish a ticket-detail endpoint."
        action={
          <Link className="button button-primary" to="/bookings">
            Find booking
          </Link>
        }
      />
    );
  return (
    <section className="container page-section">
      <Link to={`/bookings/${encodeURIComponent(bookingId)}`} className="back-link">
        ← Booking
      </Link>
      <Card padded className="ticket-card">
        <Ticket size={30} />
        <p className="eyebrow">Ticket reference</p>
        <h1>{ticketId}</h1>
        <Badge tone={booking.data?.ticketIds?.includes(ticketId) ? 'success' : 'warning'}>
          {booking.data?.ticketIds?.includes(ticketId) ? 'ISSUED' : 'VERIFYING'}
        </Badge>
        <div className="qr-placeholder" aria-label="QR not exposed by public contract">
          <QrCode size={80} />
        </div>
        <p className="muted">
          QR payload and check-in details are intentionally not fabricated. They can be shown after
          a public ticket contract is added to the ESB.
        </p>
      </Card>
    </section>
  );
}
