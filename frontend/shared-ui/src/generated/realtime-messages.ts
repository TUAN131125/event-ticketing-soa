// Generated from contracts/providers/realtime-status.asyncapi.yaml. Do not edit manually.
// Contract SHA-256: ea3ab1068687d075107b566a369961ad54393c17c41fa382c9d2cc0610913d33
export type paths = Record<string, never>;
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /** @enum {string} */
    BookingStatus:
      | 'PENDING'
      | 'SEAT_RESERVED'
      | 'PAYMENT_PROCESSING'
      | 'CONFIRMED'
      | 'FAILED'
      | 'CANCELLED'
      | 'COMPENSATION_PENDING';
    RealtimeClientMessage:
      | {
          /** @constant */
          type: 'authenticate';
          ticket: string;
        }
      | {
          /** @constant */
          type: 'subscribe';
          bookingId: string;
          lastSequence?: number;
        }
      | {
          /** @constant */
          type: 'unsubscribe';
          bookingId: string;
        }
      | {
          /** @constant */
          type: 'heartbeat_ack';
          heartbeatId: string;
        };
    RealtimeMessage: {
      messageId: string;
      bookingId: string;
      status: components['schemas']['BookingStatus'];
      sequence: number;
      /** Format: date-time */
      occurredAt: string;
      correlationId: string;
      message?: string;
    };
    RealtimeServerControlMessage:
      | {
          /** @constant */
          type: 'authenticated';
          bookingId: string;
          /** Format: date-time */
          authenticatedAt: string;
        }
      | {
          /** @constant */
          type: 'authentication_failed';
          /** @enum {string} */
          code: 'TICKET_EXPIRED' | 'TICKET_REUSED' | 'TICKET_INVALID' | 'ACCESS_DENIED';
          /** @constant */
          retryable: false;
        }
      | {
          /** @constant */
          type: 'resync_required';
          bookingId: string;
          authoritativeUrl: string;
          /** @enum {string} */
          reason: 'reconnect' | 'sequence_gap' | 'history_unavailable';
          lastObservedSequence?: number | null;
        }
      | {
          /** @constant */
          type: 'heartbeat';
          heartbeatId: string;
          /** Format: date-time */
          sentAt: string;
        }
      | {
          /** @constant */
          type: 'connected';
          bookingId: string;
        }
      | {
          /** @constant */
          type: 'shutdown';
          /** @constant */
          retryable: true;
        }
      | {
          /** @constant */
          type: 'protocol_error';
          code: string;
          message: string;
        };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export type operations = Record<string, never>;
