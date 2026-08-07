// Generated from contracts/providers/realtime-status-service.yaml. Do not edit manually.
// Contract SHA-256: 13ba0548b3f0488e2ea8ddab2258af0fcfa61b0dd13d3cd215878b69a43c1fa1
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
    /** Accept a non-authoritative booking status projection */
    post: operations['ingestRealtimeStatusEvent'];
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
    /** @enum {string} */
    BookingStatus:
      | 'PENDING'
      | 'SEAT_RESERVED'
      | 'PAYMENT_PROCESSING'
      | 'CONFIRMED'
      | 'FAILED'
      | 'CANCELLED'
      | 'COMPENSATION_PENDING';
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
    StatusEventResult: {
      /** @enum {string} */
      outcome: 'ACCEPTED' | 'DUPLICATE' | 'STALE';
      messageId: string;
      bookingId: string;
      sequence: number;
      correlationId: string;
    };
    ErrorResponse: {
      correlationId: string;
      traceId?: string;
      error: {
        code: string;
        message: string;
        retryable: boolean;
      };
    };
    HealthStatus: {
      /** @enum {string} */
      status: 'UP' | 'READY' | 'NOT_READY';
      service?: string;
      version?: string;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  ingestRealtimeStatusEvent: {
    parameters: {
      query?: never;
      header?: {
        'X-Correlation-ID'?: string;
        traceparent?: string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['RealtimeMessage'];
      };
    };
    responses: {
      /** @description Duplicate or stale status was ignored */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['StatusEventResult'];
        };
      };
      /** @description New status accepted for broadcast */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['StatusEventResult'];
        };
      };
      /** @description Invalid service identity */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ErrorResponse'];
        };
      };
      /** @description Invalid status event */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ErrorResponse'];
        };
      };
    };
  };
  realtimeLiveness: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Process is alive */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HealthStatus'];
        };
      };
    };
  };
  realtimeReadiness: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Service is ready */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HealthStatus'];
        };
      };
      /** @description Service is not ready */
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
}
