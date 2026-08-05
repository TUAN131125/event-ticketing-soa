// Generated from contracts/realtime-service.openapi.yaml. Do not edit manually.
export interface paths {
  '/internal/status-events': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Accept a booking status projection from an internal producer
     * @description Accepts a non-authoritative status projection for best-effort broadcast. messageId is the deduplication identity and sequence is monotonic per bookingId. Duplicate or stale input is not broadcast again. The caller presents a short-lived signed service JWT whose iss, sub, aud, iat, exp and jti are verified. aud must identify Realtime Status Service, sub must be allow-listed and replayed jti values are rejected. Browser JWTs are forbidden; deployment mTLS may supplement but not replace this contract.
     */
    post: operations['ingestRealtimeStatusEvent'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/connections/health': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Read non-sensitive aggregate connection health
     * @description Returns only aggregate connection and backend readiness information. It never returns tokens, booking subscription identifiers, customer identifiers, user identifiers or message content.
     */
    get: operations['getConnectionHealth'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/health/live': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Process liveness probe */
    get: operations['realtimeLiveness'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/health/ready': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Dependency readiness probe */
    get: operations['realtimeReadiness'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /**
     * @example {
     *       "correlationId": "corr-1234567890abcdef",
     *       "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
     *       "error": {
     *         "code": "RESOURCE_CONFLICT",
     *         "message": "The resource changed; reload and retry.",
     *         "retryable": false,
     *         "details": {
     *           "currentVersion": 3
     *         }
     *       }
     *     }
     */
    ErrorResponse: {
      correlationId: string;
      traceId?: string;
      error: {
        code: string;
        message: string;
        retryable: boolean;
        details?: {
          [key: string]: unknown;
        };
      };
    };
    StatusEventResult: {
      /** @enum {string} */
      outcome: 'ACCEPTED' | 'DUPLICATE' | 'STALE';
      messageId: string;
      bookingId: string;
      sequence: number;
      correlationId: string;
    };
    ConnectionHealth: {
      /** @enum {string} */
      status: 'UP' | 'DEGRADED';
      activeConnections: number;
      activeBookingChannels: number;
      /** @enum {string} */
      broadcastBackend: 'memory' | 'redis';
      backendAvailable: boolean;
      draining: boolean;
    };
    /**
     * @example {
     *       "amountMinor": 250000,
     *       "currency": "VND"
     *     }
     */
    Money: {
      /** Format: int64 */
      amountMinor: number;
      currency: string;
    };
    /**
     * @example {
     *       "status": "READY"
     *     }
     */
    HealthStatus: {
      /** @enum {string} */
      status: 'UP' | 'READY' | 'NOT_READY';
      service?: string;
      version?: string;
    };
  };
  responses: {
    /** @description Malformed request. */
    BadRequest: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Authentication failed. */
    Unauthorized: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description The authenticated principal is not authorized. */
    Forbidden: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Service or required dependency is unavailable. */
    ServiceUnavailable: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Resource not found. */
    NotFound: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Idempotency, uniqueness or state conflict. */
    Conflict: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description If-Match does not match the current ETag. */
    PreconditionFailed: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Request violates validation or domain rules. */
    Unprocessable: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Unexpected server failure. */
    InternalError: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
  };
  parameters: {
    /** @example corr-1234567890abcdef */
    CorrelationId: string;
    /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
    Traceparent: string;
    /** @example idem-booking-12345678 */
    IdempotencyKey: string;
    /** @example "3" */
    IfMatch: string;
  };
  requestBodies: never;
  headers: {
    /**
     * @description Strong resource-version validator used by If-Match.
     * @example "3"
     */
    ETag: string;
  };
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  ingestRealtimeStatusEvent: {
    parameters: {
      query?: never;
      header?: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': {
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
      };
    };
    responses: {
      /** @description Valid event identified as duplicate or stale and not broadcast. */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['StatusEventResult'];
        };
      };
      /** @description New event accepted for best-effort publication. */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          /**
           * @example {
           *       "outcome": "ACCEPTED",
           *       "messageId": "MSG-001",
           *       "bookingId": "BKG-001",
           *       "sequence": 3,
           *       "correlationId": "corr-1234567890abcdef"
           *     }
           */
          'application/json': components['schemas']['StatusEventResult'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      /** @description Invalid status, sequence, timestamp or identifier. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ErrorResponse'];
        };
      };
      /** @description Temporary broadcast backend failure; booking processing is unaffected. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ErrorResponse'];
        };
      };
    };
  };
  getConnectionHealth: {
    parameters: {
      query?: never;
      header?: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Aggregate connection health. */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          /**
           * @example {
           *       "status": "UP",
           *       "activeConnections": 12,
           *       "activeBookingChannels": 5,
           *       "broadcastBackend": "memory",
           *       "backendAvailable": true,
           *       "draining": false
           *     }
           */
          'application/json': components['schemas']['ConnectionHealth'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  realtimeLiveness: {
    parameters: {
      query?: never;
      header?: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Process is running. */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          /**
           * @example {
           *       "status": "UP"
           *     }
           */
          'application/json': components['schemas']['HealthStatus'];
        };
      };
    };
  };
  realtimeReadiness: {
    parameters: {
      query?: never;
      header?: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Service is ready. */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          /**
           * @example {
           *       "status": "READY"
           *     }
           */
          'application/json': components['schemas']['HealthStatus'];
        };
      };
      503: components['responses']['ServiceUnavailable'];
    };
  };
}
