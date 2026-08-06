import { useMemo, useState, type ChangeEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowRight, Info, LayoutGrid, RefreshCw, Ticket } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Select,
  Spinner,
} from '@event-ticketing/shared-ui';
import { useEvent, useSeatMap } from '../app/hooks';
import { ApiError } from '../api/auth-client';
import { ApiErrorDetails } from '../components/common/ApiErrorDetails';
import { QueryState } from './PageState';
import { writeCheckoutDraft } from '../utils/checkout-draft';

function formatMoney(amountMinor: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amountMinor);
}

export function SeatSelectionPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const event = useEvent(eventId);
  const seatMap = useSeatMap(eventId);
  const [selected, setSelected] = useState<string[]>([]);
  const [ticketType, setTicketType] = useState('');

  const seats = useMemo(() => {
    const source = seatMap.data?.seats ?? [];
    return ticketType ? source.filter((seat) => seat.ticketTypeId === ticketType) : source;
  }, [seatMap.data, ticketType]);

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

  const currentEvent = event.data;
  const seatMapError = seatMap.error instanceof ApiError ? seatMap.error : null;

  const toggleSeat = (seatId: string) => {
    setSelected((current) => {
      if (current.includes(seatId)) return current.filter((id) => id !== seatId);
      if (current.length >= 10) return current;
      return [...current, seatId];
    });
  };

  const continueCheckout = () => {
    const draft = writeCheckoutDraft({
      eventId: currentEvent.eventId,
      eventName: currentEvent.name,
      seatIds: selected,
    });
    navigate('/checkout/contact', { state: draft });
  };

  return (
    <section className="container page-section">
      <Link to={`/events/${encodeURIComponent(currentEvent.eventId)}`} className="back-link">
        ← {currentEvent.name}
      </Link>
      <div className="page-heading split-heading">
        <div>
          <p className="eyebrow">Step 1 of 3</p>
          <h1>Choose your seats</h1>
          <p className="lede">
            Availability is read from the ESB seat-map projection. The browser never decides that a
            seat is available and never calls the SOAP service directly.
          </p>
        </div>
        <Button
          variant="secondary"
          disabled={seatMap.isFetching}
          onClick={() => void seatMap.refetch()}
        >
          <RefreshCw size={17} /> {seatMap.isFetching ? 'Refreshing…' : 'Refresh availability'}
        </Button>
      </div>

      {currentEvent.ticketTypes.length > 0 && (
        <Card padded className="seat-filter-card">
          <label htmlFor="ticket-type-filter">
            <strong>Ticket type</strong>
          </label>
          <Select
            id="ticket-type-filter"
            value={ticketType}
            onChange={(inputEvent: ChangeEvent<HTMLSelectElement>) => setTicketType(inputEvent.target.value)}
          >
            <option value="">All ticket types</option>
            {currentEvent.ticketTypes.map((value, index) => (
              <option key={value.ticketTypeId ?? index} value={value.ticketTypeId ?? ''}>
                {value.name ?? `Ticket type ${index + 1}`}
              </option>
            ))}
          </Select>
        </Card>
      )}

      {seatMap.isLoading ? (
        <div className="page-state">
          <Spinner label="Loading seat availability" />
        </div>
      ) : seatMap.isError ? (
        <Card padded className="seat-map-unavailable">
          <LayoutGrid size={36} />
          <div>
            <h2>Seat map unavailable</h2>
            <p className="muted">
              {seatMapError?.message ?? 'Try refreshing the authoritative seat projection.'}
            </p>
            <ApiErrorDetails error={seatMap.error} />
            <Button variant="secondary" onClick={() => void seatMap.refetch()}>
              Retry
            </Button>
          </div>
        </Card>
      ) : seats.length ? (
        <div className="detail-layout seat-selection-layout">
          <Card padded className="detail-main">
            <div className="seat-map-legend" aria-label="Seat status legend">
              <span><i className="seat-dot is-available" /> Available</span>
              <span><i className="seat-dot is-selected" /> Selected</span>
              <span><i className="seat-dot is-unavailable" /> Held or sold</span>
            </div>
            <div className="seat-map-grid" role="group" aria-label="Available seats">
              {seats.map((seat) => {
                const isAvailable = seat.status === 'AVAILABLE';
                const isSelected = selected.includes(seat.seatId);
                return (
                  <button
                    key={seat.seatId}
                    type="button"
                    className={`seat-button ${isSelected ? 'is-selected' : ''}`}
                    disabled={!isAvailable}
                    aria-pressed={isSelected}
                    aria-label={`${seat.seatCode}, ${seat.status}${seat.ticketTypeName ? `, ${seat.ticketTypeName}` : ''}`}
                    onClick={() => toggleSeat(seat.seatId)}
                  >
                    <strong>{seat.seatCode}</strong>
                    <small>{seat.section ?? seat.row ?? seat.status}</small>
                  </button>
                );
              })}
            </div>
          </Card>

          <Card padded className="booking-panel">
            <h2>Selection summary</h2>
            <p>
              <Ticket size={16} /> {selected.length} seat{selected.length === 1 ? '' : 's'}
            </p>
            <div className="selected-seat-list" aria-live="polite">
              {selected.length ? (
                selected.map((seatId) => {
                  const seat = seatMap.data?.seats.find((item) => item.seatId === seatId);
                  return (
                    <div className="selected-seat-row" key={seatId}>
                      <Badge tone="brand">{seat?.seatCode ?? seatId}</Badge>
                      <span>{seat?.ticketTypeName ?? 'Ticket'}</span>
                      {seat?.price && (
                        <strong>{formatMoney(seat.price.amountMinor, seat.price.currency)}</strong>
                      )}
                    </div>
                  );
                })
              ) : (
                <p className="muted">Select up to ten available seats.</p>
              )}
            </div>
            <Alert tone="info" title="Final validation happens during booking">
              <Info size={16} /> Availability can change. Seat Inventory revalidates the selection
              atomically when the booking command is submitted.
            </Alert>
            <Button fullWidth disabled={selected.length === 0} onClick={continueCheckout}>
              Continue <ArrowRight size={17} />
            </Button>
          </Card>
        </div>
      ) : (
        <EmptyState
          title="No seats available"
          description="Try another ticket type or refresh the seat map."
          action={
            <Button variant="secondary" onClick={() => void seatMap.refetch()}>
              Refresh seat map
            </Button>
          }
        />
      )}
    </section>
  );
}
