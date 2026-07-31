export interface StatusEvent { type: string; eventId: string; bookingId: string; status: string; sequence: number; occurredAt: string; message?: string; }

export class BookingStatusSocket {
  private socket: WebSocket | null = null;
  private closedByClient = false;
  constructor(private readonly url: string, private readonly token: string | null) {}
  connect(onMessage: (event: StatusEvent) => void, onState: (state: 'connecting' | 'open' | 'closed' | 'error') => void): () => void {
    this.closedByClient = false; onState('connecting');
    const separator = this.url.includes('?') ? '&' : '?';
    this.socket = new WebSocket(this.token ? `${this.url}${separator}access_token=${encodeURIComponent(this.token)}` : this.url);
    this.socket.onopen = () => onState('open');
    this.socket.onerror = () => onState('error');
    this.socket.onclose = () => onState('closed');
    this.socket.onmessage = (message) => { try { onMessage(JSON.parse(message.data as string) as StatusEvent); } catch { /* malformed messages are ignored */ } };
    return () => { this.closedByClient = true; this.socket?.close(1000, 'client disconnect'); this.socket = null; };
  }
}

export function statusSocketUrl(bookingId: string): string {
  const configured = (import.meta.env.VITE_REALTIME_WS_URL ?? '').replace(/\/$/, '');
  return configured ? `${configured}/ws/bookings/${encodeURIComponent(bookingId)}` : '';
}
