import { describe, expect, it, vi } from 'vitest';
import { EsbClient } from '../src/api/esb-client';
import {
  describeBookingStatus,
  isReconciling,
  isSettled,
  isKnownBookingStatus,
} from '../src/domain/booking-status';

const bookingBody = (status: string) => ({
  bookingId: 'BK-1',
  status,
  total: { amountMinor: 250000, currency: 'VND' },
  reservationId: 'RSV-1',
  paymentId: null,
  ticketIds: [],
  correlationId: 'corr-1',
});

const jsonResponse = (body: unknown, init: ResponseInit) =>
  new Response(JSON.stringify(body), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });

describe('booking submission outcomes', () => {
  it('reports a 202 as reconciling and carries the server poll interval', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse(bookingBody('PAYMENT_PROCESSING'), {
        status: 202,
        headers: { Location: '/api/bookings/BK-1', 'Retry-After': '5', ETag: '"2"' },
      }),
    );
    const client = new EsbClient({ baseUrl: 'https://esb.example', fetchImpl });
    const submission = await client.createBooking(
      {
        customerId: 'CUST-1',
        eventId: 'EV001',
        seatIds: ['A01'],
        paymentMethodToken: 'tok_demo_success',
      },
      'idem-12345678',
    );
    expect(submission.reconciling).toBe(true);
    expect(submission.retryAfterSeconds).toBe(5);
    expect(submission.statusPath).toBe('/api/bookings/BK-1');
    expect(submission.booking.status).toBe('PAYMENT_PROCESSING');
    expect(fetchImpl).toHaveBeenCalledTimes(1); // the command is never resent
    const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Headers).get('Idempotency-Key')).toBe('idem-12345678');
  });

  it('reports a 201 as settled', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(bookingBody('CONFIRMED'), { status: 201, headers: { ETag: '"1"' } }),
      );
    const client = new EsbClient({ baseUrl: 'https://esb.example', fetchImpl });
    const submission = await client.createBooking(
      {
        customerId: 'CUST-1',
        eventId: 'EV001',
        seatIds: ['A01'],
        paymentMethodToken: 'tok_demo_success',
      },
      'idem-12345678',
    );
    expect(submission.reconciling).toBe(false);
    expect(submission.retryAfterSeconds).toBeNull();
  });

  it('sends the authoritative ETag as If-Match when cancelling', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(bookingBody('SEAT_RESERVED'), { status: 200, headers: { ETag: '"4"' } }),
      )
      .mockResolvedValueOnce(
        jsonResponse(bookingBody('CANCELLED'), { status: 200, headers: { ETag: '"5"' } }),
      );
    const client = new EsbClient({ baseUrl: 'https://esb.example', fetchImpl });
    await client.cancelBooking('BK-1', 'idem-cancel-1234');
    const [url, init] = fetchImpl.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('https://esb.example/api/bookings/BK-1/cancel');
    expect((init.headers as Headers).get('If-Match')).toBe('"4"');
  });

  it('refuses to cancel when no authoritative version is readable', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse(bookingBody('SEAT_RESERVED'), { status: 200 }));
    const client = new EsbClient({ baseUrl: 'https://esb.example', fetchImpl });
    await expect(client.cancelBooking('BK-1')).rejects.toMatchObject({
      code: 'PRECONDITION_REQUIRED',
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe('booking status semantics', () => {
  it('treats PAYMENT_PROCESSING as an unsettled reconciliation state', () => {
    expect(isReconciling('PAYMENT_PROCESSING')).toBe(true);
    expect(isSettled('PAYMENT_PROCESSING')).toBe(false);
    expect(describeBookingStatus('PAYMENT_PROCESSING').inProgress).toBe(true);
  });

  it('treats CONFIRMED, FAILED and CANCELLED as settled', () => {
    expect(['CONFIRMED', 'FAILED', 'CANCELLED'].every(isSettled)).toBe(true);
  });

  it('falls back safely for a status the contract does not enumerate', () => {
    expect(isKnownBookingStatus('PENDING_RECONCILIATION')).toBe(false);
    const view = describeBookingStatus('PENDING_RECONCILIATION');
    expect(view.tone).toBe('neutral');
    expect(view.inProgress).toBe(false);
    expect(view.label).toBe('PENDING_RECONCILIATION');
  });
});
