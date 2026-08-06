import type {
  BookingListProjection,
  BookingResult,
  CustomerProfileInput,
  CustomerProfileProjection,
  PlaceBookingRequest,
  PublicEvent,
  RealtimeWsTicket,
  SeatMapProjection,
  TicketListProjection,
  TicketProjection,
} from '@event-ticketing/shared-ui/frontend-esb-contract';
import { ApiError } from './auth-client';

export type { PlaceBookingRequest, RealtimeWsTicket } from '@event-ticketing/shared-ui/frontend-esb-contract';

export type ContractEvent = PublicEvent;
export type ContractBooking = BookingResult;
export type TicketType = PublicEvent['ticketTypes'][number];
export type EventSummary = ContractEvent;
export type Booking = ContractBooking;

export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface BookingSubmission {
  booking: Booking;
  reconciling: boolean;
  retryAfterSeconds: number | null;
  statusPath: string | null;
}

export const DEFAULT_BOOKING_POLL_SECONDS = 3;
export const DEFAULT_HTTP_TIMEOUT_MS = 15_000;

const bookingContextKey = (bookingId: string) => `evently.booking.${bookingId}`;
const bookingIndexKey = 'evently.bookingIds';

function rememberBookingContext(booking: Booking, _request?: PlaceBookingRequest): Booking {
  try {
    sessionStorage.setItem(bookingContextKey(booking.bookingId), JSON.stringify(booking));
    const ids = JSON.parse(localStorage.getItem(bookingIndexKey) ?? '[]') as unknown;
    const list = Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : [];
    localStorage.setItem(
      bookingIndexKey,
      JSON.stringify(
        [booking.bookingId, ...list.filter((id) => id !== booking.bookingId)].slice(0, 20),
      ),
    );
  } catch {
    // Storage is a navigation convenience only. Booking state is always reloaded from the ESB.
  }
  return booking;
}

function mergeStoredContext(booking: ContractBooking): Booking {
  return booking;
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
  private readonly timeoutMs: number;
  private readonly bookingEtags = new Map<string, string>();

  constructor(
    options: {
      baseUrl?: string;
      fetchImpl?: typeof fetch;
      getToken?: () => string | null;
      timeoutMs?: number;
    } = {},
  ) {
    this.baseUrl = (options.baseUrl ?? String(import.meta.env.VITE_ESB_API_URL ?? '')).replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
    this.getToken = options.getToken ?? (() => null);
    this.timeoutMs = options.timeoutMs ?? DEFAULT_HTTP_TIMEOUT_MS;
  }

  async listEvents(
    params: { query?: string; status?: string; page?: number; pageSize?: number } = {},
  ): Promise<Page<EventSummary>> {
    const events = (await this.request<ContractEvent[]>('/api/events')).body.map((event) =>
      this.normaliseEvent(event),
    );
    const query = params.query?.trim().toLocaleLowerCase();
    const status = params.status?.trim().toLocaleUpperCase();
    const filtered = events.filter((event) => {
      const searchText = `${event.name} ${event.venue} ${event.status}`.toLocaleLowerCase();
      const matchesQuery = !query || searchText.includes(query);
      const matchesStatus = !status || event.status.toLocaleUpperCase() === status;
      return matchesQuery && matchesStatus;
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

  async getCustomerProfile(): Promise<CustomerProfileProjection> {
    const result = await this.request<CustomerProfileProjection>('/api/me/customer');
    return result.body;
  }

  async upsertCustomerProfile(
    payload: CustomerProfileInput,
    idempotencyKey: string = crypto.randomUUID(),
  ): Promise<CustomerProfileProjection> {
    const result = await this.request<CustomerProfileProjection>('/api/me/customer', {
      method: 'PUT',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(payload),
    });
    return result.body;
  }

  /** Canonical UI-03 ESB facade. The browser never calls the SOAP Seat service directly. */
  async getSeatMap(eventId: string): Promise<SeatMapProjection> {
    return (
      await this.request<SeatMapProjection>(
        `/api/events/${encodeURIComponent(eventId)}/seat-map`,
      )
    ).body;
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

  /** Canonical owner-scoped booking list facade. */
  async listBookings(page = 1, pageSize = 20): Promise<BookingListProjection> {
    const search = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    const result = await this.request<BookingListProjection>(
      `/api/bookings?${search.toString()}`,
    );
    return {
      ...result.body,
      items: result.body.items.map((booking) => mergeStoredContext(booking)),
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
    reason: string,
    idempotencyKey: string = crypto.randomUUID(),
  ): Promise<Booking> {
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
        body:
          import.meta.env.VITE_ESB_CANCEL_REASON_ENABLED === 'true'
            ? JSON.stringify({ reason })
            : undefined,
      },
    );
    this.rememberEtag(bookingId, result.etag);
    return rememberBookingContext(mergeStoredContext(result.body));
  }

  /** Canonical owner-scoped ticket list facade for UI-08. */
  async listTickets(page = 1, pageSize = 20): Promise<TicketListProjection> {
    const search = new URLSearchParams({ page: String(page), pageSize: String(pageSize) });
    return (await this.request<TicketListProjection>(`/api/tickets?${search.toString()}`)).body;
  }

  /** Canonical owner-scoped ticket detail facade for UI-08. */
  async getTicket(ticketId: string): Promise<TicketProjection> {
    return (await this.request<TicketProjection>(`/api/tickets/${encodeURIComponent(ticketId)}`))
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
    return event;
  }

  private rememberEtag(bookingId: string, etag: string | null): void {
    if (etag) this.bookingEtags.set(bookingId, etag);
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
  ): Promise<{ body: T; etag: string | null; status: number; headers: Headers }> {
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

    const controller = new AbortController();
    const timer = globalThis.setTimeout(() => controller.abort(), this.timeoutMs);
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: 'include',
        signal: init.signal ?? controller.signal,
      });
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') {
        throw new ApiError(
          504,
          {
            error: {
              code: 'SERVICE_TIMEOUT',
              message: 'The ESB did not respond before the request deadline.',
              retryable: true,
            },
          },
          'The ESB did not respond before the request deadline.',
          { cause },
        );
      }
      throw this.unavailable('ESB is temporarily unavailable.', cause);
    } finally {
      globalThis.clearTimeout(timer);
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
