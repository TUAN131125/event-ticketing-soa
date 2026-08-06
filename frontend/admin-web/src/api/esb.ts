import type {
  AdminEventInput,
  AdminEventProjection,
  AdminSeatInventoryProjection,
  ConfigureSeatInventoryRequest,
  ConfigureSeatInventoryResult,
  AggregateHealth,
  CheckInResult,
  PublicEvent,
  TicketValidationResult,
  TraceSteps,
} from '@event-ticketing/shared-ui/frontend-esb-contract';
import { ApiError, request, requestWithMetadata } from './http';

export type { AggregateHealth, PublicEvent } from '@event-ticketing/shared-ui/frontend-esb-contract';

export type TraceStep = TraceSteps[number];

const esbBase = () => String(import.meta.env.VITE_ESB_API_URL ?? '');

export class EsbAdminClient {
  private readonly base: string;
  private readonly eventEtags = new Map<string, string>();
  private readonly ticketEtags = new Map<string, string>();

  constructor(baseUrl = esbBase()) {
    this.base = baseUrl.replace(/\/$/, '');
  }

  events(accessToken: string): Promise<PublicEvent[]> {
    return request(this.base, '/api/events', { accessToken });
  }

  async event(accessToken: string, id: string): Promise<AdminEventProjection> {
    const result = await requestWithMetadata<AdminEventProjection>(
      this.base,
      `/api/events/${encodeURIComponent(id)}`,
      { accessToken },
    );
    if (result.etag) this.eventEtags.set(id, result.etag);
    return result.body;
  }

  createEvent(accessToken: string, payload: AdminEventInput): Promise<AdminEventProjection> {
    return request(this.base, '/api/admin/events', {
      method: 'POST',
      accessToken,
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: payload,
    });
  }

  async replaceEvent(
    accessToken: string,
    eventId: string,
    payload: AdminEventInput,
  ): Promise<AdminEventProjection> {
    if (!this.eventEtags.has(eventId)) await this.event(accessToken, eventId);
    const ifMatch = this.eventEtags.get(eventId);
    if (!ifMatch)
      throw new ApiError('The event version is unavailable, so the update cannot be sent safely', {
        status: 428,
        code: 'PRECONDITION_REQUIRED',
        retryable: true,
      });
    const result = await requestWithMetadata<AdminEventProjection>(
      this.base,
      `/api/admin/events/${encodeURIComponent(eventId)}`,
      {
        method: 'PUT',
        accessToken,
        headers: {
          'Idempotency-Key': crypto.randomUUID(),
          'If-Match': ifMatch,
        },
        body: payload,
      },
    );
    if (result.etag) this.eventEtags.set(eventId, result.etag);
    return result.body;
  }

  async transitionEvent(
    accessToken: string,
    eventId: string,
    action: 'publish' | 'pause' | 'close' | 'cancel',
  ): Promise<AdminEventProjection> {
    if (!this.eventEtags.has(eventId)) await this.event(accessToken, eventId);
    const ifMatch = this.eventEtags.get(eventId);
    if (!ifMatch)
      throw new ApiError('The event version is unavailable, so the command cannot be sent safely', {
        status: 428,
        code: 'PRECONDITION_REQUIRED',
        retryable: true,
      });
    const result = await requestWithMetadata<AdminEventProjection>(
      this.base,
      `/api/admin/events/${encodeURIComponent(eventId)}/${action}`,
      {
        method: 'POST',
        accessToken,
        headers: {
          'Idempotency-Key': crypto.randomUUID(),
          'If-Match': ifMatch,
        },
      },
    );
    if (result.etag) this.eventEtags.set(eventId, result.etag);
    return result.body;
  }

  seatInventory(
    accessToken: string,
    eventId: string,
  ): Promise<AdminSeatInventoryProjection> {
    return request(
      this.base,
      `/api/admin/events/${encodeURIComponent(eventId)}/seat-inventory`,
      { accessToken },
    );
  }

  configureSeatInventory(
    accessToken: string,
    eventId: string,
    payload: ConfigureSeatInventoryRequest,
  ): Promise<ConfigureSeatInventoryResult> {
    return request(
      this.base,
      `/api/admin/events/${encodeURIComponent(eventId)}/seat-inventory`,
      {
        method: 'PUT',
        accessToken,
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: payload,
      },
    );
  }

  async validateTicket(accessToken: string, qrToken: string): Promise<TicketValidationResult> {
    const result = await requestWithMetadata<TicketValidationResult>(
      this.base,
      '/api/check-in/validate',
      { method: 'POST', accessToken, body: { qrToken } },
    );
    const ticketId = result.body.ticket?.ticketId;
    if (ticketId && result.etag) this.ticketEtags.set(ticketId, result.etag);
    return result.body;
  }

  async checkInTicket(
    accessToken: string,
    ticketId: string,
    qrToken: string,
  ): Promise<CheckInResult> {
    const ifMatch = this.ticketEtags.get(ticketId);
    if (!ifMatch)
      throw new ApiError('The validated ticket version is unavailable, so check-in cannot be sent', {
        status: 428,
        code: 'PRECONDITION_REQUIRED',
        retryable: true,
      });
    const headers: Record<string, string> = {
      'Idempotency-Key': crypto.randomUUID(),
      'If-Match': ifMatch,
    };
    const result = await requestWithMetadata<CheckInResult>(
      this.base,
      `/api/check-in/tickets/${encodeURIComponent(ticketId)}`,
      { method: 'POST', accessToken, headers, body: { qrToken } },
    );
    if (result.etag) this.ticketEtags.set(ticketId, result.etag);
    return result.body;
  }

  health(accessToken: string): Promise<AggregateHealth> {
    return request(this.base, '/api/health', { accessToken, acceptStatuses: [503] });
  }

  traces(accessToken: string, correlationId: string): Promise<TraceStep[]> {
    return request(this.base, `/api/traces/${encodeURIComponent(correlationId)}`, {
      accessToken,
    });
  }
}

export const esbAdminClient = new EsbAdminClient();
