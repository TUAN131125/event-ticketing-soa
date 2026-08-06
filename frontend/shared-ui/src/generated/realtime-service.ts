// Generated from contracts/providers/realtime-status-service.yaml. Do not edit manually.
// Contract SHA-256: 13ba0548b3f0488e2ea8ddab2258af0fcfa61b0dd13d3cd215878b69a43c1fa1
// Generator: frontend/scripts/generate_esb_types.py

export interface paths {
  "/internal/status-events": { parameters: { query?: never; header?: never; path?: never; cookie?: never; }; get?: never; put?: never; post: operations["ingestRealtimeStatusEvent"]; delete?: never; patch?: never; options?: never; head?: never; trace?: never; };
  "/health/live": { parameters: { query?: never; header?: never; path?: never; cookie?: never; }; get: operations["realtimeLiveness"]; put?: never; post?: never; delete?: never; patch?: never; options?: never; head?: never; trace?: never; };
  "/health/ready": { parameters: { query?: never; header?: never; path?: never; cookie?: never; }; get: operations["realtimeReadiness"]; put?: never; post?: never; delete?: never; patch?: never; options?: never; head?: never; trace?: never; };
}

export type webhooks = Record<string, never>;

export interface components {
  schemas: {
    BookingStatus: "PENDING" | "SEAT_RESERVED" | "PAYMENT_PROCESSING" | "CONFIRMED" | "FAILED" | "CANCELLED" | "COMPENSATION_PENDING";
    RealtimeMessage: { messageId: string; bookingId: string; status: components['schemas']["BookingStatus"]; sequence: number; occurredAt: string; correlationId: string; message?: string; };
    StatusEventResult: { outcome: "ACCEPTED" | "DUPLICATE" | "STALE"; messageId: string; bookingId: string; sequence: number; correlationId: string; };
    ErrorResponse: { correlationId: string; traceId?: string; error: { code: string; message: string; retryable: boolean; }; };
    HealthStatus: { status: "UP" | "READY" | "NOT_READY"; service?: string; version?: string; };
  };
  responses: Record<string, never>;
  parameters: Record<string, never>;
  requestBodies: Record<string, never>;
  headers: Record<string, never>;
  pathItems: Record<string, never>;
}

export interface operations {
  ingestRealtimeStatusEvent: { parameters: { query?: never; header: { "X-Correlation-ID"?: string; traceparent?: string; }; path?: never; cookie?: never; }; requestBody: { content: { "application/json": components['schemas']["RealtimeMessage"]; }; }; responses: { "202": { headers: Record<string, never>; content: { "application/json": components['schemas']["StatusEventResult"]; }; }; "200": { headers: Record<string, never>; content: { "application/json": components['schemas']["StatusEventResult"]; }; }; "401": { headers: Record<string, never>; content: { "application/json": components['schemas']["ErrorResponse"]; }; }; "422": { headers: Record<string, never>; content: { "application/json": components['schemas']["ErrorResponse"]; }; }; }; };
  realtimeLiveness: { parameters: { query?: never; header?: never; path?: never; cookie?: never; }; requestBody?: never; responses: { "200": { headers: Record<string, never>; content: { "application/json": components['schemas']["HealthStatus"]; }; }; }; };
  realtimeReadiness: { parameters: { query?: never; header?: never; path?: never; cookie?: never; }; requestBody?: never; responses: { "200": { headers: Record<string, never>; content: { "application/json": components['schemas']["HealthStatus"]; }; }; "503": { headers: Record<string, never>; content: { "application/json": components['schemas']["ErrorResponse"]; }; }; }; };
}

export type $defs = Record<string, never>;
