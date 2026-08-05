import { ApiError, normalisePage, request } from './http';
import type {
  AdminOverview,
  BookingRecord,
  EventInput,
  EventRecord,
  ListParams,
  NotificationRecord,
  Page,
  PaymentRecord,
  TraceRecord,
  User,
} from '../types';

const esbBase = () => import.meta.env.VITE_ESB_API_URL || '';
const query = (params: ListParams) => {
  const search = new URLSearchParams();
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize) search.set('pageSize', String(params.pageSize));
  if (params.search) search.set('search', params.search);
  if (params.status) search.set('status', params.status);
  const value = search.toString();
  return value ? `?${value}` : '';
};
const unwrap = <T>(payload: unknown): T => {
  if (typeof payload === 'object' && payload !== null && 'data' in payload)
    return (payload as { data: T }).data;
  return payload as T;
};

export class EsbAdminClient {
  private readonly base = esbBase();
  private auth(accessToken: string) {
    return { accessToken };
  }
  async overview(accessToken: string): Promise<AdminOverview> {
    return unwrap(await request(this.base, '/api/admin/overview', { ...this.auth(accessToken) }));
  }
  async events(accessToken: string, params: ListParams): Promise<Page<EventRecord>> {
    return normalisePage<EventRecord>(
      await request(this.base, `/api/events${query(params)}`, { ...this.auth(accessToken) }),
      params.page,
      params.pageSize,
    );
  }
  async event(accessToken: string, id: string): Promise<EventRecord> {
    return unwrap(
      await request(this.base, `/api/events/${encodeURIComponent(id)}`, {
        ...this.auth(accessToken),
      }),
    );
  }
  async createEvent(accessToken: string, input: EventInput): Promise<EventRecord> {
    return unwrap(
      await request(this.base, '/api/events', {
        method: 'POST',
        body: input,
        ...this.auth(accessToken),
      }),
    );
  }
  async updateEvent(
    accessToken: string,
    id: string,
    input: Partial<EventInput>,
  ): Promise<EventRecord> {
    return unwrap(
      await request(this.base, `/api/events/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: input,
        ...this.auth(accessToken),
      }),
    );
  }
  async publishEvent(accessToken: string, id: string): Promise<void> {
    await request(this.base, `/api/events/${encodeURIComponent(id)}/publish`, {
      method: 'POST',
      body: {},
      ...this.auth(accessToken),
    });
  }
  async bookings(accessToken: string, params: ListParams): Promise<Page<BookingRecord>> {
    return normalisePage<BookingRecord>(
      await request(this.base, `/api/bookings${query(params)}`, { ...this.auth(accessToken) }),
      params.page,
      params.pageSize,
    );
  }
  async booking(accessToken: string, id: string): Promise<BookingRecord> {
    return unwrap(
      await request(this.base, `/api/bookings/${encodeURIComponent(id)}`, {
        ...this.auth(accessToken),
      }),
    );
  }
  async cancelBooking(accessToken: string, id: string): Promise<void> {
    await request(this.base, `/api/bookings/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
      body: {},
      ...this.auth(accessToken),
    });
  }
  async refundBooking(accessToken: string, id: string): Promise<void> {
    await request(this.base, `/api/bookings/${encodeURIComponent(id)}/refund`, {
      method: 'POST',
      body: {},
      ...this.auth(accessToken),
    });
  }
  async payments(accessToken: string, params: ListParams): Promise<Page<PaymentRecord>> {
    return normalisePage<PaymentRecord>(
      await request(this.base, `/api/payments${query(params)}`, { ...this.auth(accessToken) }),
      params.page,
      params.pageSize,
    );
  }
  async notifications(accessToken: string, params: ListParams): Promise<Page<NotificationRecord>> {
    return normalisePage<NotificationRecord>(
      await request(this.base, `/api/notifications${query(params)}`, { ...this.auth(accessToken) }),
      params.page,
      params.pageSize,
    );
  }
  async traces(accessToken: string, params: ListParams): Promise<Page<TraceRecord>> {
    return normalisePage<TraceRecord>(
      await request(this.base, `/api/monitoring/traces${query(params)}`, {
        ...this.auth(accessToken),
      }),
      params.page,
      params.pageSize,
    );
  }
  async users(accessToken: string, params: ListParams): Promise<Page<User>> {
    return normalisePage<User>(
      await request(this.base, `/api/admin/users${query(params)}`, { ...this.auth(accessToken) }),
      params.page,
      params.pageSize,
    );
  }
}

export const esbAdminClient = new EsbAdminClient();

export const isUnavailable = (error: unknown) =>
  error instanceof ApiError &&
  (error.code === 'SERVICE_UNAVAILABLE' ||
    error.code === 'SERVICE_TIMEOUT' ||
    error.status >= 500 ||
    error.status === 0);
