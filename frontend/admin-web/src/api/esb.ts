import type { components } from '@event-ticketing/shared-ui/esb-contract';
import { ApiError, request, requestWithMetadata } from './http';

export type PublicEvent = components['schemas']['PublicEvent'];
export type BookingResult = components['schemas']['BookingResult'];
export type TraceStep = components['schemas']['TraceStep'];
export type AggregateHealth = components['schemas']['AggregateHealth'];

const esbBase = () => import.meta.env.VITE_ESB_API_URL || '';

export class EsbAdminClient {
  private readonly base: string;
  private readonly bookingEtags = new Map<string, string>();

  constructor(baseUrl = esbBase()) {
    this.base = baseUrl.replace(/\/$/, '');
  }

  events(accessToken: string): Promise<PublicEvent[]> {
    return request(this.base, '/api/events', { accessToken });
  }

  event(accessToken: string, id: string): Promise<PublicEvent> {
    return request(this.base, `/api/events/${encodeURIComponent(id)}`, { accessToken });
  }

  async booking(accessToken: string, id: string): Promise<BookingResult> {
    const result = await requestWithMetadata<BookingResult>(
      this.base,
      `/api/bookings/${encodeURIComponent(id)}`,
      { accessToken },
    );
    if (result.etag) this.bookingEtags.set(id, result.etag);
    return result.body;
  }

  async cancelBooking(accessToken: string, id: string): Promise<BookingResult> {
    // The contract makes If-Match required, so the authoritative ETag is read first.
    if (!this.bookingEtags.has(id)) await this.booking(accessToken, id);
    const ifMatch = this.bookingEtags.get(id);
    if (!ifMatch)
      throw new ApiError('The booking version is unavailable, so cancellation cannot be sent', {
        status: 428,
        code: 'PRECONDITION_REQUIRED',
        retryable: true,
      });
    const result = await requestWithMetadata<BookingResult>(
      this.base,
      `/api/bookings/${encodeURIComponent(id)}/cancel`,
      {
        method: 'POST',
        accessToken,
        headers: { 'Idempotency-Key': crypto.randomUUID(), 'If-Match': ifMatch },
      },
    );
    if (result.etag) this.bookingEtags.set(id, result.etag);
    return result.body;
  }

  health(accessToken: string): Promise<AggregateHealth> {
    // A DOWN aggregate is reported as 503 with the same documented body.
    return request(this.base, '/api/health', { accessToken, acceptStatuses: [503] });
  }

  traces(accessToken: string, correlationId: string): Promise<TraceStep[]> {
    return request(this.base, `/api/traces/${encodeURIComponent(correlationId)}`, {
      accessToken,
    });
  }
}

export const esbAdminClient = new EsbAdminClient();
