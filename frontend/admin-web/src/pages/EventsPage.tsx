import { useEffect, useState, type MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { Plus, RefreshCw, Settings2 } from 'lucide-react';
import { ConfirmationDialog } from '@event-ticketing/shared-ui';
import { ApiError } from '../api/http';
import { esbAdminClient, type PublicEvent } from '../api/esb';
import { StatusBadge } from '../components/StatusBadge';

export function EventsPage({
  accessToken,
  compact = false,
}: {
  accessToken: string;
  compact?: boolean;
}) {
  const [events, setEvents] = useState<PublicEvent[]>([]);
  const [selected, setSelected] = useState<PublicEvent | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<
    { event: PublicEvent; action: 'publish' | 'pause' | 'close' | 'cancel' } | undefined
  >();

  const load = () => {
    setBusy(true);
    setError(null);
    void esbAdminClient
      .events(accessToken)
      .then((value) => {
        setEvents(value);
        setSelected((current) => value.find((item) => item.eventId === current?.eventId) ?? value[0] ?? null);
      })
      .catch((value: Error) => setError(value))
      .finally(() => setBusy(false));
  };

  useEffect(load, [accessToken]);

  const transition = () => {
    if (!pendingAction) return;
    setBusy(true);
    setError(null);
    void esbAdminClient
      .transitionEvent(accessToken, pendingAction.event.eventId, pendingAction.action)
      .then(() => {
        setPendingAction(undefined);
        load();
      })
      .catch((value: Error) => setError(value))
      .finally(() => setBusy(false));
  };

  const api = error instanceof ApiError ? error : null;

  return (
    <section className={compact ? '' : 'events-screen-grid'}>
      <div className="card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">UI-10 · Event administration</p>
            <h3>Events</h3>
          </div>
          <div className="page-actions">
            {!compact && (
              <Link className="native-button" to="/events/new">
                <Plus size={16} /> Create event
              </Link>
            )}
            <button className="native-button secondary-button" onClick={load} disabled={busy}>
              <RefreshCw size={16} /> Refresh
            </button>
          </div>
        </div>
        {error && (
          <div className="form-error" role="alert">
            <strong>{error.message}</strong>
            {api?.code && <span>Error code: {api.code}</span>}
            {api?.correlationId && <span>Correlation ID: {api.correlationId}</span>}
          </div>
        )}
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Venue</th>
                <th>Starts at</th>
                <th>Status</th>
                {!compact && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {events.map((item) => (
                <tr
                  key={item.eventId}
                  className={selected?.eventId === item.eventId ? 'is-selected' : undefined}
                  onClick={() => !compact && setSelected(item)}
                >
                  <td className="table-primary">{item.name}</td>
                  <td>{item.venue}</td>
                  <td>{new Date(item.startsAt).toLocaleString()}</td>
                  <td><StatusBadge value={item.status} /></td>
                  {!compact && (
                    <td>
                      <div className="table-actions">
                        <Link
                          className="icon-link"
                          to={`/events/${encodeURIComponent(item.eventId)}/edit`}
                          aria-label={`Edit ${item.name}`}
                        >
                          <Settings2 size={16} />
                        </Link>
                        {['DRAFT', 'PAUSED'].includes(item.status) && (
                          <button
                            type="button"
                            className="text-button"
                            onClick={(event: MouseEvent<HTMLButtonElement>) => {
                              event.stopPropagation();
                              setPendingAction({ event: item, action: 'publish' });
                            }}
                          >
                            Publish
                          </button>
                        )}
                        {item.status === 'ON_SALE' && (
                          <button
                            type="button"
                            className="text-button"
                            onClick={(event: MouseEvent<HTMLButtonElement>) => {
                              event.stopPropagation();
                              setPendingAction({ event: item, action: 'pause' });
                            }}
                          >
                            Pause
                          </button>
                        )}
                        {['ON_SALE', 'PAUSED'].includes(item.status) && (
                          <button
                            type="button"
                            className="text-button"
                            onClick={(event: MouseEvent<HTMLButtonElement>) => {
                              event.stopPropagation();
                              setPendingAction({ event: item, action: 'close' });
                            }}
                          >
                            Close
                          </button>
                        )}
                        {!['ENDED', 'CANCELLED'].includes(item.status) && (
                          <button
                            type="button"
                            className="text-button danger-text"
                            onClick={(event: MouseEvent<HTMLButtonElement>) => {
                              event.stopPropagation();
                              setPendingAction({ event: item, action: 'cancel' });
                            }}
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!events.length && !busy && <p className="muted">No events were returned by the ESB.</p>}
      </div>

      {!compact && (
        <div className="card event-inspector">
          {selected ? (
            <>
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Selected event</p>
                  <h3>{selected.name}</h3>
                </div>
                <StatusBadge value={selected.status} />
              </div>
              <dl className="detail-list">
                <div><dt>Event ID</dt><dd>{selected.eventId}</dd></div>
                <div><dt>Venue</dt><dd>{selected.venue}</dd></div>
                <div><dt>Starts</dt><dd>{new Date(selected.startsAt).toLocaleString()}</dd></div>
                <div><dt>Ticket types</dt><dd>{selected.ticketTypes.length}</dd></div>
              </dl>
              <Link className="native-button" to={`/events/${encodeURIComponent(selected.eventId)}/edit`}>
                Edit event
              </Link>
            </>
          ) : (
            <p className="muted">Select an event to inspect it.</p>
          )}
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(pendingAction)}
        title={`${pendingAction?.action ?? 'Update'} event?`}
        onClose={() => setPendingAction(undefined)}
        onConfirm={transition}
        loading={busy}
        tone={pendingAction?.action === 'cancel' ? 'danger' : 'primary'}
        confirmLabel="Confirm"
      >
        <p>
          This command is sent through the ESB with idempotency and optimistic concurrency. Event
          Service remains authoritative for legal state transitions.
        </p>
      </ConfirmationDialog>
    </section>
  );
}
