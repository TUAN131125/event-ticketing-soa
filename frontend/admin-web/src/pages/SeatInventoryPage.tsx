import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Save, Trash2 } from 'lucide-react';
import type { ConfigureSeatInventoryRequest } from '@event-ticketing/shared-ui/frontend-esb-contract';
import { ApiError } from '../api/http';
import { esbAdminClient } from '../api/esb';

const emptySeat = (): ConfigureSeatInventoryRequest['seats'][number] => ({
  seatId: '',
  section: 'MAIN',
  rowLabel: 'A',
  seatNumber: '',
  ticketTypeId: '',
  status: 'AVAILABLE',
});

export function SeatInventoryPage({
  accessToken,
  eventId,
}: {
  accessToken: string;
  eventId: string;
}) {
  const [inventoryVersion, setInventoryVersion] = useState(1);
  const [seats, setSeats] = useState<ConfigureSeatInventoryRequest['seats']>([emptySeat()]);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);

  useEffect(() => {
    setBusy(true);
    void esbAdminClient
      .seatInventory(accessToken, eventId)
      .then((inventory) => {
        if (inventory.seats.length) {
          setSeats(
            inventory.seats.map((seat) => ({
              seatId: seat.seatId,
              section: seat.section ?? 'MAIN',
              rowLabel: seat.row ?? 'A',
              seatNumber: seat.seatCode,
              ticketTypeId: seat.ticketTypeId,
              status: seat.status === 'AVAILABLE' ? 'AVAILABLE' : 'BLOCKED',
            })),
          );
        }
      })
      .catch((cause: Error) => setError(cause))
      .finally(() => setBusy(false));
  }, [accessToken, eventId]);

  const update = (
    index: number,
    patch: Partial<ConfigureSeatInventoryRequest['seats'][number]>,
  ) => {
    setSeats((current) =>
      current.map((seat, seatIndex) => (seatIndex === index ? { ...seat, ...patch } : seat)),
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    void esbAdminClient
      .configureSeatInventory(accessToken, eventId, { inventoryVersion, seats })
      .then((result) => {
        setInventoryVersion(result.inventoryVersion + 1);
        setMessage(`${result.configuredSeatCount} seats ${result.status.toLowerCase()}.`);
      })
      .catch((cause: Error) => setError(cause))
      .finally(() => setBusy(false));
  };

  const api = error instanceof ApiError ? error : null;

  return (
    <section>
      <div className="page-header">
        <div>
          <p className="eyebrow">UC-14 · Seat inventory</p>
          <h2>Seat map and capacity</h2>
          <p className="page-description">
            The ESB only converts this JSON request to SOAP ConfigureInventory. Seat Inventory
            Service remains authoritative for inventory version, protected seats and state rules.
          </p>
        </div>
        <Link className="native-button secondary-button" to={`/events/${encodeURIComponent(eventId)}/edit`}>
          Back to event
        </Link>
      </div>

      <form className="event-form-layout" onSubmit={submit}>
        <div className="card form-card-grid">
          <label>
            <span>Inventory version</span>
            <input
              className="native-input"
              type="number"
              min="1"
              value={inventoryVersion}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setInventoryVersion(Math.max(1, Number(event.target.value)))
              }
            />
          </label>
          <div className="form-actions">
            <button
              className="native-button secondary-button"
              type="button"
              onClick={() => setSeats((current) => [...current, emptySeat()])}
            >
              <Plus size={16} /> Add seat
            </button>
          </div>
        </div>

        <div className="card">
          <div className="ticket-type-editor-list">
            {seats.map((seat, index) => (
              <div className="ticket-type-editor" key={`${seat.seatId}-${index}`}>
                <label>
                  <span>Seat ID</span>
                  <input className="native-input" required value={seat.seatId} onChange={(event) => update(index, { seatId: event.target.value })} />
                </label>
                <label>
                  <span>Section</span>
                  <input className="native-input" required value={seat.section} onChange={(event) => update(index, { section: event.target.value })} />
                </label>
                <label>
                  <span>Row</span>
                  <input className="native-input" required value={seat.rowLabel} onChange={(event) => update(index, { rowLabel: event.target.value })} />
                </label>
                <label>
                  <span>Seat number</span>
                  <input className="native-input" required value={seat.seatNumber} onChange={(event) => update(index, { seatNumber: event.target.value })} />
                </label>
                <label>
                  <span>Ticket type</span>
                  <input className="native-input" required value={seat.ticketTypeId} onChange={(event) => update(index, { ticketTypeId: event.target.value.trim().toUpperCase() })} />
                </label>
                <label>
                  <span>Status</span>
                  <select className="native-input" value={seat.status} onChange={(event) => update(index, { status: event.target.value as 'AVAILABLE' | 'BLOCKED' })}>
                    <option value="AVAILABLE">AVAILABLE</option>
                    <option value="BLOCKED">BLOCKED</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="icon-link danger-text"
                  aria-label={`Remove seat ${index + 1}`}
                  disabled={seats.length === 1}
                  onClick={() => setSeats((current) => current.filter((_, seatIndex) => seatIndex !== index))}
                >
                  <Trash2 size={17} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {message && <div className="form-success" role="status">{message}</div>}
        {error && (
          <div className="form-error" role="alert">
            <strong>{error.message}</strong>
            {api?.code && <span>Error code: {api.code}</span>}
            {api?.correlationId && <span>Correlation ID: {api.correlationId}</span>}
          </div>
        )}

        <div className="form-actions">
          <button className="native-button" type="submit" disabled={busy}>
            <Save size={16} /> {busy ? 'Saving…' : 'Configure inventory'}
          </button>
        </div>
      </form>
    </section>
  );
}
