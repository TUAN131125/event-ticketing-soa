import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, Save, Trash2 } from 'lucide-react';
import type {
  AdminEventInput,
  AdminTicketTypeInput,
} from '@event-ticketing/shared-ui/frontend-esb-contract';
import { ApiError } from '../api/http';
import { esbAdminClient } from '../api/esb';

const emptyTicketType = (): AdminTicketTypeInput => ({
  ticketTypeId: '',
  name: '',
  price: { amountMinor: 0, currency: 'VND' },
});

const initialEvent = (): AdminEventInput => ({
  name: '',
  venue: '',
  startsAt: '',
  saleStartsAt: '',
  saleEndsAt: '',
  ticketTypes: [emptyTicketType()],
});

const toLocalDateTime = (value?: string | null) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

const toIso = (value: string) => new Date(value).toISOString();

export function EventFormPage({
  accessToken,
  eventId,
}: {
  accessToken: string;
  eventId?: string;
}) {
  const navigate = useNavigate();
  const [value, setValue] = useState<AdminEventInput>(initialEvent);
  const [busy, setBusy] = useState(Boolean(eventId));
  const [error, setError] = useState<ApiError | Error | null>(null);

  useEffect(() => {
    if (!eventId) return;
    setBusy(true);
    setError(null);
    void esbAdminClient
      .event(accessToken, eventId)
      .then((event) =>
        setValue({
          name: event.name,
          venue: event.venue,
          startsAt: toLocalDateTime(event.startsAt),
          saleStartsAt: toLocalDateTime(event.saleStartsAt),
          saleEndsAt: toLocalDateTime(event.saleEndsAt),
          ticketTypes: event.ticketTypes.length ? event.ticketTypes : [emptyTicketType()],
        }),
      )
      .catch((cause: Error) => setError(cause))
      .finally(() => setBusy(false));
  }, [accessToken, eventId]);

  const updateTicketType = (index: number, patch: Partial<AdminTicketTypeInput>) => {
    setValue((current) => ({
      ...current,
      ticketTypes: current.ticketTypes.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...patch } : item,
      ),
    }));
  };

  const submit = (formEvent: FormEvent) => {
    formEvent.preventDefault();
    setError(null);
    const payload: AdminEventInput = {
      ...value,
      startsAt: toIso(value.startsAt),
      saleStartsAt: toIso(value.saleStartsAt),
      saleEndsAt: toIso(value.saleEndsAt),
      ticketTypes: value.ticketTypes.map((ticketType) => ({
        ...ticketType,
        name: ticketType.name.trim(),
        price: {
          amountMinor: Number(ticketType.price.amountMinor),
          currency: ticketType.price.currency.trim().toUpperCase(),
        },
      })),
    };
    setBusy(true);
    const request = eventId
      ? esbAdminClient.replaceEvent(accessToken, eventId, payload)
      : esbAdminClient.createEvent(accessToken, payload);
    void request
      .then((event) => navigate(`/events/${encodeURIComponent(event.eventId)}/edit`, { replace: true }))
      .catch((cause: Error) => setError(cause))
      .finally(() => setBusy(false));
  };

  const api = error instanceof ApiError ? error : null;

  return (
    <section>
      <div className="page-header">
        <div>
          <p className="eyebrow">UI-10 · Admin event</p>
          <h2>{eventId ? 'Update event' : 'Create event'}</h2>
          <p className="page-description">
            The form sends only documented Event fields through the canonical ESB admin facade.
          </p>
        </div>
        <div className="form-actions">
          {eventId && (
            <Link className="native-button secondary-button" to={`/events/${encodeURIComponent(eventId)}/seats`}>
              Manage seat inventory
            </Link>
          )}
          <Link className="native-button secondary-button" to="/events">Back to events</Link>
        </div>
      </div>

      <form className="event-form-layout" onSubmit={submit}>
        <div className="card form-card-grid">
          <label>
            <span>Event name</span>
            <input
              className="native-input"
              value={value.name}
              required
              maxLength={160}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setValue((current) => ({ ...current, name: event.target.value }))}
            />
          </label>
          <label>
            <span>Venue</span>
            <input
              className="native-input"
              value={value.venue}
              required
              maxLength={200}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setValue((current) => ({ ...current, venue: event.target.value }))}
            />
          </label>
          <label>
            <span>Event starts at</span>
            <input
              className="native-input"
              type="datetime-local"
              value={value.startsAt}
              required
              onChange={(event: ChangeEvent<HTMLInputElement>) => setValue((current) => ({ ...current, startsAt: event.target.value }))}
            />
          </label>
          <label>
            <span>Sale starts at</span>
            <input
              className="native-input"
              type="datetime-local"
              value={value.saleStartsAt}
              required
              onChange={(event: ChangeEvent<HTMLInputElement>) => setValue((current) => ({ ...current, saleStartsAt: event.target.value }))}
            />
          </label>
          <label>
            <span>Sale ends at</span>
            <input
              className="native-input"
              type="datetime-local"
              value={value.saleEndsAt}
              required
              onChange={(event: ChangeEvent<HTMLInputElement>) => setValue((current) => ({ ...current, saleEndsAt: event.target.value }))}
            />
          </label>
        </div>

        <div className="card">
          <div className="section-heading">
            <div><p className="eyebrow">Published pricing</p><h3>Ticket types</h3></div>
            <button
              className="native-button secondary-button"
              type="button"
              onClick={() => setValue((current) => ({ ...current, ticketTypes: [...current.ticketTypes, emptyTicketType()] }))}
            >
              <Plus size={16} /> Add type
            </button>
          </div>
          <div className="ticket-type-editor-list">
            {value.ticketTypes.map((ticketType, index) => (
              <div className="ticket-type-editor" key={ticketType.ticketTypeId || index}>
                <label>
                  <span>Code</span>
                  <input
                    className="native-input"
                    value={ticketType.ticketTypeId}
                    required
                    maxLength={64}
                    placeholder="STD"
                    onChange={(event: ChangeEvent<HTMLInputElement>) =>
                      updateTicketType(index, { ticketTypeId: event.target.value.trim().toUpperCase() })
                    }
                  />
                </label>
                <label>
                  <span>Name</span>
                  <input
                    className="native-input"
                    value={ticketType.name}
                    required
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateTicketType(index, { name: event.target.value })}
                  />
                </label>
                <label>
                  <span>Amount minor</span>
                  <input
                    className="native-input"
                    type="number"
                    min="0"
                    step="1"
                    value={ticketType.price.amountMinor}
                    required
                    onChange={(event: ChangeEvent<HTMLInputElement>) =>
                      updateTicketType(index, {
                        price: { ...ticketType.price, amountMinor: Number(event.target.value) },
                      })
                    }
                  />
                </label>
                <label>
                  <span>Currency</span>
                  <input
                    className="native-input"
                    value={ticketType.price.currency}
                    required
                    maxLength={3}
                    onChange={(event: ChangeEvent<HTMLInputElement>) =>
                      updateTicketType(index, {
                        price: { ...ticketType.price, currency: event.target.value },
                      })
                    }
                  />
                </label>
                <button
                  type="button"
                  className="icon-link danger-text"
                  aria-label={`Remove ticket type ${index + 1}`}
                  disabled={value.ticketTypes.length === 1}
                  onClick={() =>
                    setValue((current) => ({
                      ...current,
                      ticketTypes: current.ticketTypes.filter((_, itemIndex) => itemIndex !== index),
                    }))
                  }
                >
                  <Trash2 size={17} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <div className="form-error" role="alert">
            <strong>{error.message}</strong>
            {api?.code && <span>Error code: {api.code}</span>}
            {api?.correlationId && <span>Correlation ID: {api.correlationId}</span>}
          </div>
        )}

        <div className="form-actions">
          <button className="native-button" type="submit" disabled={busy}>
            <Save size={16} /> {busy ? 'Saving…' : eventId ? 'Save changes' : 'Create event'}
          </button>
        </div>
      </form>
    </section>
  );
}
