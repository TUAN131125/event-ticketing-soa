// Generated from contracts/realtime-service.asyncapi.yaml. Do not edit manually.
export type paths = Record<string, never>;
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /**
     * RealtimeClientMessage
     * @description Realtime client frames. authenticate with an ESB-issued signed one-time JWT/JWS ticket is mandatory before subscribe; long-lived access tokens and customerId are forbidden.
     * @example {
     *       "type": "authenticate",
     *       "ticket": "example-not-a-real-ticket"
     *     }
     * @example {
     *       "type": "subscribe",
     *       "bookingId": "BKG-001",
     *       "lastSequence": 2
     *     }
     * @example {
     *       "type": "unsubscribe",
     *       "bookingId": "BKG-001"
     *     }
     */
    RealtimeClientMessage:
      | {
          /** @constant */
          type: 'authenticate';
          /** @description Signed short-lived single-use JWT/JWS ticket; never log or place in a URL. */
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
    /**
     * RealtimeMessage
     * @description Best-effort non-authoritative booking status projection.
     * @example {
     *       "messageId": "MSG-001",
     *       "bookingId": "BKG-001",
     *       "status": "PAYMENT_PROCESSING",
     *       "sequence": 3,
     *       "occurredAt": "2026-08-03T03:00:00Z",
     *       "correlationId": "corr-1234567890abcdef",
     *       "message": "Payment result is being verified"
     *     }
     */
    RealtimeMessage: {
      messageId: string;
      bookingId: string;
      /** @enum {unknown} */
      status:
        | 'PENDING'
        | 'SEAT_RESERVED'
        | 'PAYMENT_PROCESSING'
        | 'CONFIRMED'
        | 'FAILED'
        | 'CANCELLED'
        | 'COMPENSATION_PENDING';
      sequence: number;
      /** Format: date-time */
      occurredAt: string;
      correlationId: string;
      message?: string;
    };
    /**
     * RealtimeServerControlMessage
     * @description Realtime authentication, reconnect, resync, heartbeat and lifecycle controls. Authentication failures never expose raw tickets or token details.
     * @example {
     *       "type": "authenticated",
     *       "bookingId": "BKG-001",
     *       "authenticatedAt": "2026-08-03T03:00:05Z"
     *     }
     * @example {
     *       "type": "authentication_failed",
     *       "code": "TICKET_EXPIRED",
     *       "retryable": false
     *     }
     * @example {
     *       "type": "authentication_failed",
     *       "code": "TICKET_REUSED",
     *       "retryable": false
     *     }
     * @example {
     *       "type": "resync_required",
     *       "bookingId": "BKG-001",
     *       "authoritativeUrl": "/api/bookings/BKG-001",
     *       "reason": "sequence_gap",
     *       "lastObservedSequence": 3
     *     }
     */
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
