import { ApiError } from './auth-client';

export interface EventSummary { eventId: string; name: string; venue?: string; startsAt?: string; endsAt?: string; status?: string; imageUrl?: string; description?: string; category?: string; }
export interface Seat { seatId: string; label?: string; section?: string; row?: string; number?: string | number; status: string; price?: number; currency?: string; }
export interface SeatMap { eventId: string; seats: Seat[]; inventoryVersion?: number; }
export interface Reservation { reservationId: string; bookingId?: string; eventId: string; seatIds: string[]; status: string; expiresAt?: string; total?: number; currency?: string; }
export interface Booking { bookingId: string; eventId?: string; status: string; total?: number; currency?: string; createdAt?: string; seats?: string[]; ticketIds?: string[]; event?: EventSummary; }
export interface Ticket { ticketId: string; bookingId: string; status: string; qrCode?: string; seatLabel?: string; event?: EventSummary; }
export interface Page<T> { items: T[]; page: number; pageSize: number; total: number; }
export interface RealtimeWsTicket { ticket: string; bookingId: string; expiresAt: string; }

function asObject(value: unknown): Record<string, unknown> { return value && typeof value === 'object' ? value as Record<string, unknown> : {}; }
function text(value: unknown, fallback = ''): string { return typeof value === 'string' ? value : fallback; }
function array<T>(value: unknown): T[] { return Array.isArray(value) ? value as T[] : []; }

export class EsbClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly getToken: () => string | null;
  constructor(options: { baseUrl?: string; fetchImpl?: typeof fetch; getToken?: () => string | null } = {}) {
    this.baseUrl = (options.baseUrl ?? import.meta.env.VITE_ESB_API_URL ?? '').replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.getToken = options.getToken ?? (() => null);
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.baseUrl) throw new ApiError(503, { error: { code: 'SERVICE_UNAVAILABLE', message: 'Event services are not configured.', retryable: true } });
    const headers = new Headers(init.headers);
    headers.set('Accept', 'application/json');
    headers.set('X-Correlation-ID', crypto.randomUUID());
    const token = this.getToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    let response: Response;
    try { response = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers, credentials: 'include' }); }
    catch { throw new ApiError(503, { error: { code: 'SERVICE_UNAVAILABLE', message: 'Event services are temporarily unavailable.', retryable: true } }); }
    if (!response.ok) {
      let payload: Record<string, unknown> | undefined;
      try { payload = await response.json() as Record<string, unknown>; } catch { /* empty response */ }
      const nested = asObject(payload?.error);
      throw new ApiError(response.status, { correlationId: text(payload?.correlationId), traceId: text(payload?.traceId), error: { code: text(nested.code, text(payload?.code, response.status === 404 ? 'NOT_FOUND' : 'REQUEST_FAILED')), message: text(nested.message, text(payload?.message, 'Event service request failed.')), retryable: Boolean(nested.retryable) } });
    }
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch { throw new ApiError(503, { error: { code: 'SERVICE_UNAVAILABLE', message: 'Event services are temporarily unavailable.', retryable: true } }); }
  }

  private normaliseEvent(value: unknown): EventSummary {
    const item = asObject(value);
    return { eventId: text(item.eventId, text(item.id)), name: text(item.name, text(item.title, 'Untitled event')), venue: text(item.venue), startsAt: text(item.startsAt, text(item.startTime)), endsAt: text(item.endsAt, text(item.endTime)), status: text(item.status), imageUrl: text(item.imageUrl, text(item.coverUrl)), description: text(item.description), category: text(item.category) };
  }

  async listEvents(params: { query?: string; category?: string; from?: string; to?: string; page?: number; pageSize?: number } = {}): Promise<Page<EventSummary>> {
    const search = new URLSearchParams();
    if (params.query) search.set('q', params.query);
    if (params.category) search.set('category', params.category);
    if (params.from) search.set('from', params.from);
    if (params.to) search.set('to', params.to);
    search.set('page', String(params.page ?? 1)); search.set('pageSize', String(params.pageSize ?? 12));
    const payload = await this.request<unknown>(`/api/events?${search}`);
    const raw = asObject(payload);
    const items = (Array.isArray(payload) ? payload : array<unknown>(raw.items ?? raw.data)).map((x) => this.normaliseEvent(x));
    return { items, page: Number(raw.page ?? params.page ?? 1), pageSize: Number(raw.pageSize ?? params.pageSize ?? 12), total: Number(raw.total ?? items.length) };
  }

  async getEvent(eventId: string): Promise<EventSummary> { return this.normaliseEvent(await this.request(`/api/events/${encodeURIComponent(eventId)}`)); }

  async getSeatMap(eventId: string): Promise<SeatMap> {
    const raw = asObject(await this.request(`/api/events/${encodeURIComponent(eventId)}/seats`));
    const seats = array<unknown>(raw.seats ?? raw.items).map((x) => { const item = asObject(x); return { seatId: text(item.seatId, text(item.id)), label: text(item.label), section: text(item.section), row: text(item.row), number: typeof item.number === 'number' || typeof item.number === 'string' ? item.number : undefined, status: text(item.status, 'UNKNOWN'), price: typeof item.price === 'number' ? item.price : undefined, currency: text(item.currency, 'VND') }; });
    return { eventId, seats, inventoryVersion: typeof raw.inventoryVersion === 'number' ? raw.inventoryVersion : undefined };
  }

  async reserveSeats(payload: { eventId: string; seatIds: string[]; bookingId?: string; idempotencyKey: string }): Promise<Reservation> { return this.request('/api/bookings/reservations', { method: 'POST', headers: { 'Idempotency-Key': payload.idempotencyKey }, body: JSON.stringify(payload) }); }
  async getReservation(reservationId: string): Promise<Reservation> { return this.request(`/api/bookings/reservations/${encodeURIComponent(reservationId)}`); }
  async extendReservation(reservationId: string, expectedVersion?: number): Promise<Reservation> { return this.request(`/api/bookings/reservations/${encodeURIComponent(reservationId)}/extend`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ expectedVersion }) }); }
  async releaseReservation(reservationId: string): Promise<void> { await this.request(`/api/bookings/reservations/${encodeURIComponent(reservationId)}/release`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } }); }
  async createBooking(payload: { eventId: string; reservationId: string; paymentMethod: string; idempotencyKey: string }): Promise<Booking> { return this.request('/api/bookings', { method: 'POST', headers: { 'Idempotency-Key': payload.idempotencyKey }, body: JSON.stringify(payload) }); }
  async listBookings(): Promise<Page<Booking>> { const payload = await this.request<unknown>('/api/bookings'); const raw = asObject(payload); const items = (Array.isArray(payload) ? payload : array<Booking>(raw.items ?? raw.data)) as Booking[]; return { items, page: Number(raw.page ?? 1), pageSize: Number(raw.pageSize ?? items.length), total: Number(raw.total ?? items.length) }; }
  async getBooking(bookingId: string): Promise<Booking> { return this.request(`/api/bookings/${encodeURIComponent(bookingId)}`); }
  async getTicket(ticketId: string): Promise<Ticket> { return this.request(`/api/tickets/${encodeURIComponent(ticketId)}`); }
  async issueRealtimeWsTicket(bookingId: string): Promise<RealtimeWsTicket> {
    return this.request('/api/realtime/ws-tickets', {
      method: 'POST',
      body: JSON.stringify({ bookingId }),
    });
  }
}
