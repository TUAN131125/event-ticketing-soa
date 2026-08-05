import type { components } from '@event-ticketing/shared-ui/esb-contract';
import { ApiError } from './auth-client';

export type ContractEvent = components['schemas']['PublicEvent'];
export type ContractBooking = components['schemas']['BookingResult'];
export type PlaceBookingRequest = components['schemas']['PlaceBookingRequest'];
export type RealtimeWsTicket = components['schemas']['WsTicketResponse'];
export type TraceStep = components['schemas']['TraceStep'];

export type TicketType = {
  ticketTypeId?: string;
  name?: string;
  price?: { amountMinor: number; currency: string };
  [key: string]: unknown;
};

export type EventSummary = Omit<ContractEvent, 'ticketTypes'> & {
  ticketTypes: TicketType[];
  description?: string;
  category?: string;
  imageUrl?: string;
};

export type Booking = ContractBooking & {
  eventId?: string;
  seatIds?: string[];
};

export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

/**
 * Result of `POST /api/bookings`. `201` is a settled outcome; `202` means the payment
 * result is still unknown and the ESB is reconciling it. The contract requires the client
 * to poll `Location` instead of resubmitting the booking command.
 */
export interface BookingSubmission {
  booking: Booking;
  reconciling: boolean;
  retryAfterSeconds: number | null;
  statusPath: string | null;
}

export const DEFAULT_BOOKING_POLL_SECONDS = 3;

const bookingContextKey = (bookingId: string) => `evently.booking.${bookingId}`;
const bookingIndexKey = 'evently.bookingIds';

function readObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function rememberBookingContext(booking: Booking, request?: PlaceBookingRequest): Booking {
  const merged: Booking = {
    ...booking,
    eventId: request?.eventId ?? booking.eventId,
    seatIds: request?.seatIds ?? booking.seatIds,
  };
  try {
    sessionStorage.setItem(bookingContextKey(booking.bookingId), JSON.stringify(merged));
    const ids = JSON.parse(localStorage.getItem(bookingIndexKey) ?? '[]') as unknown;
    const list = Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : [];
    localStorage.setItem(
      bookingIndexKey,
      JSON.stringify(
        [booking.bookingId, ...list.filter((id) => id !== booking.bookingId)].slice(0, 20),
      ),
    );
  } catch {
    // Storage is a convenience only; authoritative state always comes from the ESB.
  }
  return merged;
}

function mergeStoredContext(booking: ContractBooking): Booking {
  try {
    const raw = sessionStorage.getItem(bookingContextKey(booking.bookingId));
    if (!raw) return booking;
    const context = readObject(JSON.parse(raw));
    return {
      ...booking,
      eventId: typeof context.eventId === 'string' ? context.eventId : undefined,
      seatIds: Array.isArray(context.seatIds)
        ? context.seatIds.filter((seat): seat is string => typeof seat === 'string')
        : undefined,
    };
  } catch {
    return booking;
  }
}

export function recentBookingIds(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(bookingIndexKey) ?? '[]') as unknown;
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

export class EsbClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly getToken: () => string | null;
  private readonly bookingEtags = new Map<string, string>();

  constructor(
    options: { baseUrl?: string; fetchImpl?: typeof fetch; getToken?: () => string | null } = {},
  ) {
    this.baseUrl = (options.baseUrl ?? import.meta.env.VITE_ESB_API_URL ?? '').replace(/\/$/, '');
    // `fetch` must be called with the global as its receiver. Storing the bare function on
    // the instance and calling `this.fetchImpl(...)` makes the receiver this client, which
    // browsers reject with "Illegal invocation" before any request is sent. The wrapper also
    // keeps the lookup late so a replaced global is honoured.
    this.fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
    this.getToken = options.getToken ?? (() => null);
  }

  async listEvents(
    params: { query?: string; category?: string; page?: number; pageSize?: number } = {},
  ): Promise<Page<EventSummary>> {
    const events = (await this.request<ContractEvent[]>('/api/events')).body.map((event) =>
      this.normaliseEvent(event),
    );
    const query = params.query?.trim().toLocaleLowerCase();
    const category = params.category?.trim().toLocaleUpperCase();
    const filtered = events.filter((event) => {
      const searchText = `${event.name} ${event.venue} ${event.status}`.toLocaleLowerCase();
      const matchesQuery = !query || searchText.includes(query);
      const matchesCategory = !category || event.category?.toLocaleUpperCase() === category;
      return matchesQuery && matchesCategory;
    });
    const page = Math.max(1, params.page ?? 1);
    const pageSize = Math.max(1, params.pageSize ?? 12);
    const start = (page - 1) * pageSize;
    return {
      items: filtered.slice(start, start + pageSize),
      page,
      pageSize,
      total: filtered.length,
    };
  }

  async getEvent(eventId: string): Promise<EventSummary> {
    const result = await this.request<ContractEvent>(`/api/events/${encodeURIComponent(eventId)}`);
    return this.normaliseEvent(result.body);
  }

  async createBooking(
    payload: PlaceBookingRequest,
    idempotencyKey: string,
  ): Promise<BookingSubmission> {
    const result = await this.request<ContractBooking>('/api/bookings', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(payload),
    });
    this.rememberEtag(result.body.bookingId, result.etag);
    const retryAfter = Number.parseInt(result.headers.get('Retry-After') ?? '', 10);
    return {
      booking: rememberBookingContext(result.body, payload),
      reconciling: result.status === 202,
      retryAfterSeconds: Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
      statusPath: result.headers.get('Location'),
    };
  }

  async getBooking(bookingId: string): Promise<Booking> {
    const result = await this.request<ContractBooking>(
      `/api/bookings/${encodeURIComponent(bookingId)}`,
    );
    this.rememberEtag(bookingId, result.etag);
    return mergeStoredContext(result.body);
  }

  async cancelBooking(
    bookingId: string,
    idempotencyKey: string = crypto.randomUUID(),
  ): Promise<Booking> {
    // The contract makes If-Match required, so the authoritative ETag is read first.
    if (!this.bookingEtags.has(bookingId)) await this.getBooking(bookingId);
    const ifMatch = this.bookingEtags.get(bookingId);
    if (!ifMatch)
      throw new ApiError(428, {
        error: {
          code: 'PRECONDITION_REQUIRED',
          message: 'The booking version is unavailable, so cancellation cannot be sent safely.',
          retryable: true,
        },
      });
    const result = await this.request<ContractBooking>(
      `/api/bookings/${encodeURIComponent(bookingId)}/cancel`,
      {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey, 'If-Match': ifMatch },
      },
    );
    this.rememberEtag(bookingId, result.etag);
    return rememberBookingContext(mergeStoredContext(result.body));
  }

  async getTrace(correlationId: string): Promise<TraceStep[]> {
    return (await this.request<TraceStep[]>(`/api/traces/${encodeURIComponent(correlationId)}`))
      .body;
  }

  async issueRealtimeWsTicket(bookingId: string): Promise<RealtimeWsTicket> {
    return (
      await this.request<RealtimeWsTicket>('/api/realtime/ws-tickets', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ bookingId }),
      })
    ).body;
  }

  private normaliseEvent(event: ContractEvent): EventSummary {
    const rawTicketTypes = Array.isArray(event.ticketTypes) ? event.ticketTypes : [];
    const ticketTypes = rawTicketTypes.map((value) => readObject(value) as TicketType);
    return {
      ...event,
      ticketTypes,
      category:
        typeof ticketTypes[0]?.category === 'string' ? String(ticketTypes[0].category) : undefined,
    };
  }

  private rememberEtag(bookingId: string, etag: string | null): void {
    if (etag) this.bookingEtags.set(bookingId, etag);
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
  ): Promise<{ body: T; etag: string | null; status: number; headers: Headers }> {
    // A missing build-time URL is a deployment defect, not an unavailable service.
    if (!this.baseUrl)
      throw new ApiError(0, {
        error: {
          code: 'CONFIGURATION_ERROR',
          message: 'This build has no ESB URL configured.',
          retryable: false,
        },
      });
    const headers = new Headers(init.headers);
    headers.set('Accept', 'application/json');
    headers.set('X-Correlation-ID', crypto.randomUUID());
    const token = this.getToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    if (init.body) headers.set('Content-Type', 'application/json');
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: 'include',
      });
    } catch (cause) {
      throw this.unavailable('ESB is temporarily unavailable.', cause);
    }
    if (!response.ok) {
      const payload = (await response.json().catch(() => undefined)) as
        | {
            correlationId?: string;
            traceId?: string;
            error?: { code?: string; message?: string; retryable?: boolean };
          }
        | undefined;
      throw new ApiError(response.status, payload, 'ESB request failed.');
    }
    return {
      body: (response.status === 204 ? undefined : await response.json()) as T,
      etag: response.headers.get('ETag'),
      status: response.status,
      headers: response.headers,
    };
  }

  private unavailable(message: string, cause?: unknown): ApiError {
    return new ApiError(
      503,
      { error: { code: 'SERVICE_UNAVAILABLE', message, retryable: true } },
      message,
      { cause },
    );
  }
}
