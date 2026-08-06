import type { components } from '@event-ticketing/shared-ui/realtime-messages';
import type { RealtimeWsTicket } from './esb-client';

export type StatusEvent = components['schemas']['RealtimeMessage'];
export type ClientFrame = components['schemas']['RealtimeClientMessage'];
export type ServerControlFrame = components['schemas']['RealtimeServerControlMessage'];
export type AuthenticationFailureCode = Extract<
  ServerControlFrame,
  { type: 'authentication_failed' }
>['code'];

export type SocketState = 'connecting' | 'open' | 'closed' | 'error';

export interface TicketMode {
  /** Issues a fresh single-use ticket through the ESB for every connection attempt. */
  ticketProvider: () => Promise<RealtimeWsTicket>;
}

export interface SocketHandlers {
  onMessage: (event: StatusEvent) => void;
  onState: (state: SocketState) => void;
  /** Reload the authoritative booking from the ESB. REST always wins over this stream. */
  onResync?: (reason: 'connected' | 'resync_required') => void;
  onAuthenticationFailed?: (code: AuthenticationFailureCode) => void;
}

const RECONNECT_DELAY_MS = 500;
const MAX_RECONNECT_DELAY_MS = 15_000;

/**
 * Close codes from the AsyncAPI `x-close-codes` list that describe a rejected connection
 * rather than a transient one. Retrying them would only burn tickets.
 */
const FATAL_CLOSE_CODES = new Set([1000, 4400, 4401, 4403]);

function isServerControlFrame(value: unknown): value is ServerControlFrame {
  return Boolean(value) && typeof (value as { type?: unknown }).type === 'string';
}

function isStatusEvent(value: unknown): value is StatusEvent {
  const candidate = value as Partial<StatusEvent> | undefined;
  return (
    typeof candidate?.bookingId === 'string' &&
    typeof candidate?.status === 'string' &&
    typeof candidate?.sequence === 'number'
  );
}

/**
 * Booking status stream described by contracts/realtime-service.asyncapi.yaml.
 *
 * The connection is authenticated with an ESB-issued, booking-bound, single-use ticket sent
 * in the first `authenticate` frame. Long-lived access tokens are never placed in the URL,
 * a subprotocol or a header, and the ticket is never persisted. Each reconnect obtains a new
 * ticket and asks the caller to reload the authoritative booking over REST.
 */
export class BookingStatusSocket {
  private socket: WebSocket | null = null;
  private closedByClient = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastSequence = 0;
  private attempt = 0;

  constructor(
    private readonly url: string,
    private readonly bookingId: string,
    private readonly authentication: TicketMode,
  ) {}

  connect(handlers: SocketHandlers): () => void {
    this.closedByClient = false;
    const send = (socket: WebSocket, frame: ClientFrame): void => {
      if (socket === this.socket && socket.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify(frame));
    };

    const scheduleReconnect = (): void => {
      if (this.closedByClient) return;
      const delay = Math.min(
        MAX_RECONNECT_DELAY_MS,
        RECONNECT_DELAY_MS * 2 ** Math.min(this.attempt, 5),
      );
      this.attempt += 1;
      this.reconnectTimer = setTimeout(() => void open(), delay);
    };

    const open = async (): Promise<void> => {
      handlers.onState('connecting');
      let ticket: RealtimeWsTicket;
      try {
        ticket = await this.authentication.ticketProvider();
      } catch {
        handlers.onState('error');
        scheduleReconnect();
        return;
      }
      if (this.closedByClient) return;
      let socket: WebSocket;
      try {
        socket = new WebSocket(this.url);
      } catch {
        handlers.onState('error');
        scheduleReconnect();
        return;
      }
      this.socket = socket;
      socket.onopen = () => send(socket, { type: 'authenticate', ticket: ticket.ticket });
      socket.onerror = () => handlers.onState('error');
      socket.onclose = (event) => {
        if (socket !== this.socket) return;
        handlers.onState('closed');
        if (FATAL_CLOSE_CODES.has(event.code)) {
          this.closedByClient = true;
          return;
        }
        scheduleReconnect();
      };
      socket.onmessage = (message) => {
        let payload: unknown;
        try {
          payload = JSON.parse(message.data as string);
        } catch {
          return; // malformed frames are ignored; REST stays authoritative
        }
        if (isStatusEvent(payload)) {
          if (payload.bookingId !== this.bookingId) return;
          if (payload.sequence <= this.lastSequence) return; // stale or duplicate projection
          this.lastSequence = payload.sequence;
          handlers.onMessage(payload);
          return;
        }
        if (!isServerControlFrame(payload)) return;
        switch (payload.type) {
          case 'authenticated':
            // Subscribing replays anything missed since the last observed sequence.
            send(socket, {
              type: 'subscribe',
              bookingId: this.bookingId,
              lastSequence: this.lastSequence,
            });
            break;
          case 'connected':
            this.attempt = 0;
            handlers.onState('open');
            // A freshly established stream is never trusted as a complete history.
            handlers.onResync?.('connected');
            break;
          case 'heartbeat':
            send(socket, { type: 'heartbeat_ack', heartbeatId: payload.heartbeatId });
            break;
          case 'resync_required':
            handlers.onResync?.('resync_required');
            break;
          case 'authentication_failed':
            // The contract marks these as non-retryable: stop instead of looping.
            this.closedByClient = true;
            handlers.onAuthenticationFailed?.(payload.code);
            handlers.onState('error');
            break;
          default:
            break;
        }
      };
    };

    void open();
    return () => {
      this.closedByClient = true;
      if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
      const socket = this.socket;
      this.socket = null;
      socket?.close(1000, 'client disconnect');
    };
  }
}

export function statusSocketUrl(_bookingId: string): string {
  // Browsers only know the ESB. Until the public gateway owns a WebSocket route,
  // REST polling remains authoritative and no direct connection to port 8008 is allowed.
  return '';
}
