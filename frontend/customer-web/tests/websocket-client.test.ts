import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EsbClient } from '../src/api/esb-client';
import { BookingStatusSocket } from '../src/api/websocket-client';

class FakeWebSocket {
  static readonly OPEN = 1;
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  readonly sent: string[] = [];
  readyState = FakeWebSocket.OPEN;
  constructor(
    readonly url: string,
    readonly protocols?: string | string[],
  ) {
    FakeWebSocket.instances.push(this);
  }
  send(value: string): void {
    this.sent.push(value);
  }
  close(): void {
    this.readyState = 3;
  }
}

const ticket = (value: string) => ({ ticket: value, bookingId: 'BK-1', expiresAt: 'soon' });

describe('BookingStatusSocket ESB ticket mode', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('keeps the ticket out of the URL and becomes ready only after connected', async () => {
    const states: string[] = [];
    const provider = vi.fn().mockResolvedValue(ticket('signed-secret-ticket'));
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', 'BK-1', {
      ticketProvider: provider,
    });
    const disconnect = client.connect({
      onMessage: () => undefined,
      onState: (state) => states.push(state),
    });
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toBe('ws://realtime/ws/bookings/BK-1');
    expect(socket.url).not.toContain('signed-secret-ticket');
    expect(socket.protocols).toBeUndefined();
    expect(states).toEqual(['connecting']);
    socket.onopen?.();
    expect(JSON.parse(socket.sent[0])).toEqual({
      type: 'authenticate',
      ticket: 'signed-secret-ticket',
    });
    expect(states).toEqual(['connecting']);
    socket.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({ type: 'connected', bookingId: 'BK-1' }),
      }),
    );
    expect(states.at(-1)).toBe('open');
    disconnect();
  });

  it('subscribes from the last observed sequence once authenticated', async () => {
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', 'BK-1', {
      ticketProvider: vi.fn().mockResolvedValue(ticket('ticket-1')),
    });
    const disconnect = client.connect({ onMessage: () => undefined, onState: () => undefined });
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0];
    socket.onopen?.();
    socket.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({
          type: 'authenticated',
          bookingId: 'BK-1',
          authenticatedAt: '2026-08-03T03:00:05Z',
        }),
      }),
    );
    expect(JSON.parse(socket.sent.at(-1) as string)).toEqual({
      type: 'subscribe',
      bookingId: 'BK-1',
      lastSequence: 0,
    });
    disconnect();
  });

  it('obtains a new one-time ticket for each reconnect', async () => {
    vi.useFakeTimers();
    const provider = vi
      .fn()
      .mockResolvedValueOnce(ticket('ticket-1'))
      .mockResolvedValueOnce(ticket('ticket-2'));
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', 'BK-1', {
      ticketProvider: provider,
    });
    const disconnect = client.connect({ onMessage: () => undefined, onState: () => undefined });
    await vi.advanceTimersByTimeAsync(0);
    const first = FakeWebSocket.instances[0];
    first.onopen?.();
    first.onclose?.({ code: 1006 });
    await vi.advanceTimersByTimeAsync(500);
    expect(provider).toHaveBeenCalledTimes(2);
    const second = FakeWebSocket.instances[1];
    second.onopen?.();
    expect(JSON.parse(second.sent[0]).ticket).toBe('ticket-2');
    disconnect();
  });

  it('stops reconnecting when the server rejects the connection', async () => {
    vi.useFakeTimers();
    const provider = vi.fn().mockResolvedValue(ticket('ticket-1'));
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', 'BK-1', {
      ticketProvider: provider,
    });
    const disconnect = client.connect({ onMessage: () => undefined, onState: () => undefined });
    await vi.advanceTimersByTimeAsync(0);
    FakeWebSocket.instances[0].onclose?.({ code: 4401 });
    await vi.advanceTimersByTimeAsync(5000);
    expect(provider).toHaveBeenCalledTimes(1);
    expect(FakeWebSocket.instances).toHaveLength(1);
    disconnect();
  });

  it('answers heartbeats with the contract heartbeat_ack frame', async () => {
    const states: string[] = [];
    const onMessage = vi.fn();
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', 'BK-1', {
      ticketProvider: vi.fn().mockResolvedValue(ticket('ticket-1')),
    });
    const disconnect = client.connect({ onMessage, onState: (state) => states.push(state) });
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0];
    socket.onopen?.();
    socket.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({ type: 'connected', bookingId: 'BK-1' }),
      }),
    );
    const statesBeforeHeartbeat = [...states];
    socket.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({
          type: 'heartbeat',
          heartbeatId: 'hb-1',
          sentAt: '2026-08-03T03:00:00Z',
        }),
      }),
    );
    expect(JSON.parse(socket.sent.at(-1) as string)).toEqual({
      type: 'heartbeat_ack',
      heartbeatId: 'hb-1',
    });
    expect(onMessage).not.toHaveBeenCalled();
    expect(states).toEqual(statesBeforeHeartbeat);
    disconnect();
  });

  it('requests one authoritative REST resync without emitting status or reconnecting', async () => {
    const onMessage = vi.fn();
    const onResync = vi.fn();
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', 'BK-1', {
      ticketProvider: vi.fn().mockResolvedValue(ticket('ticket-1')),
    });
    const disconnect = client.connect({ onMessage, onState: () => undefined, onResync });
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0];
    socket.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({
          type: 'resync_required',
          reason: 'sequence_gap',
          bookingId: 'BK-1',
          authoritativeUrl: '/api/bookings/BK-1',
        }),
      }),
    );
    expect(onResync).toHaveBeenCalledWith('resync_required');
    expect(onMessage).not.toHaveBeenCalled();
    expect(FakeWebSocket.instances).toHaveLength(1);
    disconnect();
  });

  it('drops stale projections and frames for another booking', async () => {
    const onMessage = vi.fn();
    const client = new BookingStatusSocket('ws://realtime/ws/bookings/BK-1', 'BK-1', {
      ticketProvider: vi.fn().mockResolvedValue(ticket('ticket-1')),
    });
    const disconnect = client.connect({ onMessage, onState: () => undefined });
    await vi.waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const socket = FakeWebSocket.instances[0];
    const status = (bookingId: string, sequence: number) =>
      new MessageEvent('message', {
        data: JSON.stringify({
          messageId: `MSG-${sequence}`,
          bookingId,
          status: 'PAYMENT_PROCESSING',
          sequence,
          occurredAt: '2026-08-03T03:00:00Z',
          correlationId: 'corr-1',
        }),
      });
    socket.onmessage?.(status('BK-1', 2));
    socket.onmessage?.(status('BK-1', 1));
    socket.onmessage?.(status('BK-OTHER', 9));
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(onMessage.mock.calls[0][0].sequence).toBe(2);
    disconnect();
  });
});

describe('ESB WebSocket ticket request', () => {
  it('uses authenticated HTTP POST and keeps the ticket out of persistence', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ticket: 'one-time-ticket',
          bookingId: 'BK-1',
          expiresAt: '2026-08-03T03:00:30Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const client = new EsbClient({
      baseUrl: 'https://esb.example',
      fetchImpl,
      getToken: () => 'browser-access-token',
    });
    const issued = await client.issueRealtimeWsTicket('BK-1');
    expect(issued.ticket).toBe('one-time-ticket');
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://esb.example/api/realtime/ws-tickets');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ bookingId: 'BK-1' });
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer browser-access-token');
  });
});
