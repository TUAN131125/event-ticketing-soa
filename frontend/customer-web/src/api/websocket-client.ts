import type { RealtimeWsTicket } from './esb-client';

export interface StatusEvent { messageId: string; bookingId: string; status: string; sequence: number; occurredAt: string; correlationId: string; message?: string; }
export type SocketState = 'connecting' | 'open' | 'closed' | 'error';
type TicketMode = { mode?: 'esb-ticket'; ticketProvider: () => Promise<RealtimeWsTicket> };
type NativeMode = { mode: 'native-subprotocol'; token: string };

export class BookingStatusSocket {
  private socket: WebSocket | null = null;
  private closedByClient = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  constructor(private readonly url: string, private readonly authentication: TicketMode | NativeMode) {}

  connect(
    onMessage: (event: StatusEvent) => void,
    onState: (state: SocketState) => void,
    onResync?: () => void,
  ): () => void {
    this.closedByClient = false;
    const open = async (): Promise<void> => {
      onState('connecting');
      try {
        const ticket = this.authentication.mode === 'native-subprotocol'
          ? null
          : await this.authentication.ticketProvider();
        if (this.closedByClient) return;
        const protocols = this.authentication.mode === 'native-subprotocol'
          ? ['bearer', this.authentication.token]
          : undefined;
        const socket = protocols ? new WebSocket(this.url, protocols) : new WebSocket(this.url);
        this.socket = socket;
        socket.onopen = () => {
          if (ticket) socket.send(JSON.stringify({ type: 'authenticate', ticket: ticket.ticket }));
        };
        socket.onerror = () => onState('error');
        socket.onclose = () => {
          onState('closed');
          if (!this.closedByClient) this.reconnectTimer = setTimeout(() => void open(), 500);
        };
        socket.onmessage = (message) => {
          try {
            const payload = JSON.parse(message.data as string) as Record<string, unknown>;
            if (payload.type === 'connected') {
              onState('open');
            } else if (payload.type === 'heartbeat') {
              if (socket === this.socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: 'pong' }));
              }
            } else if (payload.type === 'resync_required') {
              onResync?.();
            } else if (typeof payload.bookingId === 'string' && typeof payload.status === 'string') {
              onMessage(payload as unknown as StatusEvent);
            }
          } catch { /* malformed messages are ignored */ }
        };
      } catch {
        onState('error');
        if (!this.closedByClient) this.reconnectTimer = setTimeout(() => void open(), 500);
      }
    };
    void open();
    return () => {
      this.closedByClient = true;
      if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
      this.socket?.close(1000, 'client disconnect');
      this.socket = null;
    };
  }
}

export function statusSocketUrl(bookingId: string): string {
  const configured = (import.meta.env.VITE_REALTIME_WS_URL ?? '').replace(/\/$/, '');
  return configured ? `${configured}/ws/bookings/${encodeURIComponent(bookingId)}` : '';
}
