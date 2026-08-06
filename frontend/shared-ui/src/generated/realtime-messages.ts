// Generated from contracts/providers/realtime-status.asyncapi.yaml. Do not edit manually.
// Contract SHA-256: ea3ab1068687d075107b566a369961ad54393c17c41fa382c9d2cc0610913d33
// Generator: frontend/scripts/generate_esb_types.py

export interface paths {

}

export type webhooks = Record<string, never>;

export interface components {
  schemas: {
    BookingStatus: "PENDING" | "SEAT_RESERVED" | "PAYMENT_PROCESSING" | "CONFIRMED" | "FAILED" | "CANCELLED" | "COMPENSATION_PENDING";
    RealtimeClientMessage: { type: "authenticate"; ticket: string; } | { type: "subscribe"; bookingId: string; lastSequence?: number; } | { type: "unsubscribe"; bookingId: string; } | { type: "heartbeat_ack"; heartbeatId: string; };
    RealtimeMessage: { messageId: string; bookingId: string; status: components['schemas']["BookingStatus"]; sequence: number; occurredAt: string; correlationId: string; message?: string; };
    RealtimeServerControlMessage: { type: "authenticated"; bookingId: string; authenticatedAt: string; } | { type: "authentication_failed"; code: "TICKET_EXPIRED" | "TICKET_REUSED" | "TICKET_INVALID" | "ACCESS_DENIED"; retryable: false; } | { type: "resync_required"; bookingId: string; authoritativeUrl: string; reason: "reconnect" | "sequence_gap" | "history_unavailable"; lastObservedSequence?: number | null; } | { type: "heartbeat"; heartbeatId: string; sentAt: string; } | { type: "connected"; bookingId: string; } | { type: "shutdown"; retryable: true; } | { type: "protocol_error"; code: string; message: string; };
  };
  responses: Record<string, never>;
  parameters: Record<string, never>;
  requestBodies: Record<string, never>;
  headers: Record<string, never>;
  pathItems: Record<string, never>;
}

export interface operations {

}

export type $defs = Record<string, never>;
