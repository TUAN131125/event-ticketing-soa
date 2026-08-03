import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EsbClient } from '../src/api/esb-client';
import { BookingStatusSocket } from '../src/api/websocket-client';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  readonly sent: string[] = [];
  constructor(readonly url: string, readonly protocols?: string | string[]) {
    FakeWebSocket.instances.push(this);
  }
  send(value: string): void { this.sent.push(value); }
  close(): void { /* controlled by each test */ }
}

describe('BookingStatusSocket ESB ticket mode', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('keeps the ticket out of the URL and becomes ready only after connected', async () => {
    const states: string[] = [];
    const provider = vi.fn().mockResolvedValue({
      ticket: 'signed-secret-ticket', bookingId: 'BK-1', expiresAt: '2026-08-03T03:00:30Z',
    });
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', { ticketProvider: provider });
    const disconnect = client.connect(() => undefined, (state) => states.push(state));
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toBe('ws://realtime/ws/bookings/BK-1');
    expect(socket.url).not.toContain('signed-secret-ticket');
    expect(states).toEqual(['connecting']);
    socket.onopen?.();
    expect(JSON.parse(socket.sent[0])).toEqual({ type: 'authenticate', ticket: 'signed-secret-ticket' });
    expect(states).toEqual(['connecting']);
    socket.onmessage?.(new MessageEvent('message', { data: JSON.stringify({ type: 'connected' }) }));
    expect(states.at(-1)).toBe('open');
    disconnect();
  });

  it('obtains a new one-time ticket for each reconnect', async () => {
    vi.useFakeTimers();
    const provider = vi.fn()
      .mockResolvedValueOnce({ ticket: 'ticket-1', bookingId: 'BK-1', expiresAt: 'soon' })
      .mockResolvedValueOnce({ ticket: 'ticket-2', bookingId: 'BK-1', expiresAt: 'later' });
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', { ticketProvider: provider });
    const disconnect = client.connect(() => undefined, () => undefined);
    await vi.advanceTimersByTimeAsync(0);
    const first = FakeWebSocket.instances[0];
    first.onopen?.();
    first.onclose?.();
    await vi.advanceTimersByTimeAsync(500);
    expect(provider).toHaveBeenCalledTimes(2);
    const second = FakeWebSocket.instances[1];
    second.onopen?.();
    expect(JSON.parse(second.sent[0]).ticket).toBe('ticket-2');
    disconnect();
  });
});

describe('ESB WebSocket ticket request', () => {
  it('uses authenticated HTTP POST and keeps the ticket out of persistence', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ticket: 'one-time-ticket', bookingId: 'BK-1', expiresAt: '2026-08-03T03:00:30Z',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const client = new EsbClient({
      baseUrl: 'https://esb.example',
      fetchImpl,
      getToken: () => 'browser-access-token',
    });
    const ticket = await client.issueRealtimeWsTicket('BK-1');
    expect(ticket.ticket).toBe('one-time-ticket');
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://esb.example/api/realtime/ws-tickets');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ bookingId: 'BK-1' });
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer browser-access-token');
  });
});
