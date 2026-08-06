import { useState, type ChangeEvent, type FormEvent } from 'react';
import { CheckCircle2, QrCode, RotateCcw, ScanLine } from 'lucide-react';
import type { TicketValidationResult } from '@event-ticketing/shared-ui/frontend-esb-contract';
import { ApiError } from '../api/http';
import { esbAdminClient } from '../api/esb';
import { StatusBadge } from '../components/StatusBadge';

export function CheckInPage({ accessToken }: { accessToken: string }) {
  const [qrToken, setQrToken] = useState('');
  const [validation, setValidation] = useState<TicketValidationResult | null>(null);
  const [checkedIn, setCheckedIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  const validate = (event: FormEvent) => {
    event.preventDefault();
    const token = qrToken.trim();
    if (!token) return;
    setBusy(true);
    setError(null);
    setValidation(null);
    setCheckedIn(false);
    void esbAdminClient
      .validateTicket(accessToken, token)
      .then(setValidation)
      .catch((cause: Error) => setError(cause))
      .finally(() => setBusy(false));
  };

  const checkIn = () => {
    const ticketId = validation?.ticket?.ticketId;
    if (!ticketId) return;
    setBusy(true);
    setError(null);
    void esbAdminClient
      .checkInTicket(accessToken, ticketId, qrToken.trim())
      .then((result) => {
        setValidation({ valid: true, ticket: result.ticket, correlationId: result.correlationId });
        setCheckedIn(true);
      })
      .catch((cause: Error) => setError(cause))
      .finally(() => setBusy(false));
  };

  const reset = () => {
    setQrToken('');
    setValidation(null);
    setCheckedIn(false);
    setError(null);
  };

  const api = error instanceof ApiError ? error : null;
  const ticket = validation?.ticket;

  return (
    <section>
      <div className="page-header">
        <div>
          <p className="eyebrow">UI-11 · Check-in</p>
          <h2>Validate and check in a ticket</h2>
          <p className="page-description">
            Scan or paste the QR token. Validation and duplicate-use prevention remain authoritative
            in Ticket Service through the ESB.
          </p>
        </div>
      </div>

      <div className="checkin-layout">
        <form className="card checkin-form" onSubmit={validate}>
          <div className="checkin-icon"><ScanLine size={28} /></div>
          <label htmlFor="checkin-qr"><strong>QR token</strong></label>
          <textarea
            id="checkin-qr"
            className="native-input native-textarea qr-input"
            value={qrToken}
            required
            autoFocus
            spellCheck={false}
            autoComplete="off"
            placeholder="Scan or paste the signed QR token"
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setQrToken(event.target.value)}
          />
          <p className="muted">The token is not written to logs or persistent browser storage.</p>
          <button className="native-button" type="submit" disabled={busy || !qrToken.trim()}>
            <QrCode size={16} /> {busy ? 'Validating…' : 'Validate ticket'}
          </button>
        </form>

        <div className="card checkin-result">
          {checkedIn && ticket ? (
            <div className="checkin-success">
              <CheckCircle2 size={44} />
              <p className="eyebrow">Check-in complete</p>
              <h3>{ticket.ticketId}</h3>
              <StatusBadge value={ticket.status} />
              <p>{ticket.eventName ?? ticket.eventId}</p>
              <p className="muted">Seat: {ticket.seatCode ?? ticket.seatId ?? 'General admission'}</p>
              <button className="native-button secondary-button" onClick={reset}>
                <RotateCcw size={16} /> Scan next ticket
              </button>
            </div>
          ) : ticket && validation?.valid ? (
            <>
              <div className="section-heading">
                <div><p className="eyebrow">Valid ticket</p><h3>{ticket.ticketId}</h3></div>
                <StatusBadge value={ticket.status} />
              </div>
              <dl className="detail-list">
                <div><dt>Event</dt><dd>{ticket.eventName ?? ticket.eventId}</dd></div>
                <div><dt>Booking</dt><dd>{ticket.bookingId}</dd></div>
                <div><dt>Seat</dt><dd>{ticket.seatCode ?? ticket.seatId ?? 'General admission'}</dd></div>
                <div><dt>Ticket type</dt><dd>{ticket.ticketTypeName ?? '—'}</dd></div>
              </dl>
              <button
                className="native-button"
                disabled={busy || ticket.status !== 'ISSUED'}
                onClick={checkIn}
              >
                {busy ? 'Checking in…' : 'Confirm check-in'}
              </button>
              {ticket.status !== 'ISSUED' && (
                <p className="form-error">Only an ISSUED ticket can be checked in.</p>
              )}
            </>
          ) : validation && !validation.valid ? (
            <div className="blank-inspector">
              <QrCode size={34} />
              <h3>Ticket is not valid</h3>
              <p className="form-error">{validation.message ?? validation.code ?? 'Validation failed'}</p>
              {validation.correlationId && <p className="muted">Correlation ID: {validation.correlationId}</p>}
            </div>
          ) : (
            <div className="blank-inspector">
              <QrCode size={34} />
              <h3>No ticket validated</h3>
              <p className="muted">The authoritative ticket projection will appear here.</p>
            </div>
          )}

          {error && (
            <div className="form-error" role="alert">
              <strong>{error.message}</strong>
              {api?.code && <span>Error code: {api.code}</span>}
              {api?.correlationId && <span>Correlation ID: {api.correlationId}</span>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
