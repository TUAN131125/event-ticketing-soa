// Generated from contracts/esb-public-api.yaml. Do not edit manually.
export interface paths {
  '/api/events': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Danh sách sự kiện */
    get: operations['publicListEvents'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/events/{eventId}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Chi tiết sự kiện tổng hợp */
    get: operations['publicGetEvent'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/bookings': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Đặt vé */
    post: operations['placeBooking'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/bookings/{bookingId}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Lấy trạng thái booking */
    get: operations['publicGetBooking'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/bookings/{bookingId}/cancel': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Hủy booking */
    post: operations['publicCancelBooking'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/health': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Health tổng hợp
     * @description Tổng hợp trạng thái của ESB và mọi provider. Customer, Event, Seat Inventory, Booking, Payment và Ticket là critical; Notification và Realtime là noncritical. Một critical provider DOWN trả 503/DOWN; chỉ noncritical DOWN trả 200/DEGRADED. Endpoint này không thay thế /health/ready, vốn chỉ phản ánh chính ESB.
     */
    get: operations['aggregateHealth'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/traces/{correlationId}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Tra workflow theo Correlation ID */
    get: operations['getWorkflowTrace'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/realtime/ws-tickets': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Issue a short-lived one-time Realtime WebSocket ticket
     * @description Authenticates the browser JWT, takes only bookingId, calls Booking Service's authoritative access-decision operation, and fails closed on missing/inactive mapping, denial, timeout or dependency error. The browser must never submit customerId as ownership proof. The signed JWT/JWS ticket is returned only in the response body. It is issued by booking-orchestrator, bound to bookingId, verified identity subject, scope booking:status:read and Realtime audience, has a unique jti, expires within 60 seconds, is single-use and cannot be refreshed.
     */
    post: operations['issueRealtimeWebSocketTicket'];
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
    get: operations['esbLiveness'];
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
    get: operations['esbReadiness'];
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
    SafeIdentifier: string;
    WsTicketRequest: {
      bookingId: components['schemas']['SafeIdentifier'];
    };
    WsTicketResponse: {
      /** @description Signed compact JWT/JWS credential; never place in a URL or log it. */
      ticket: string;
      bookingId: components['schemas']['SafeIdentifier'];
      /** Format: date-time */
      expiresAt: string;
    };
    /** @description Required signed JWT/JWS claims before compact serialization. */
    SignedWebSocketTicketClaims: {
      /** @constant */
      iss: 'booking-orchestrator';
      /** @constant */
      aud: 'realtime-status-service';
      sub: components['schemas']['SafeIdentifier'];
      bookingId: components['schemas']['SafeIdentifier'];
      /** @constant */
      scope: 'booking:status:read';
      /** Format: int64 */
      iat: number;
      /** Format: int64 */
      exp: number;
      jti: components['schemas']['SafeIdentifier'];
    };
    /** @description Non-wire policy assertions for every issued ticket. */
    WsTicketPolicy: {
      /** @constant */
      audience: 'realtime-status-service';
      /** @constant */
      maximumTtlSeconds: 60;
      /** @constant */
      singleUse: true;
      /** @constant */
      jtiRequired: true;
      /** @constant */
      refreshable: false;
      /** @constant */
      bookingBound: true;
      /** @constant */
      identitySubjectBound: true;
      /** @constant */
      signed: true;
      /** @constant */
      issuer: 'booking-orchestrator';
      /** @constant */
      scope: 'booking:status:read';
      /** @constant */
      requiredClaims: ['iss', 'aud', 'sub', 'bookingId', 'scope', 'iat', 'exp', 'jti'];
    };
    PublicEvent: {
      eventId: string;
      name: string;
      venue: string;
      /** Format: date-time */
      startsAt: string;
      status: string;
      ticketTypes: Record<string, never>[];
    };
    PlaceBookingRequest: {
      customerId: string;
      eventId: string;
      seatIds: string[];
      paymentMethodToken: string;
    };
    BookingResult: {
      bookingId: string;
      status: string;
      total: components['schemas']['Money'];
      reservationId?: string | null;
      paymentId?: string | null;
      ticketIds?: string[];
      correlationId: string;
    };
    TraceStep: {
      service?: string;
      operation?: string;
      status?: string;
      durationMs?: number;
      errorCode?: string | null;
    };
    DependencyHealth: {
      /** @description Logical dependency name. Never an internal URL or hostname. */
      name: string;
      critical: boolean;
      /** @enum {string} */
      status: 'UP' | 'DOWN';
      latencyMs?: number;
      /**
       * @description Stable public-safe probe code; never a provider message or stack trace.
       * @enum {string}
       */
      errorCode?: 'TIMEOUT' | 'UNREACHABLE' | 'NOT_READY';
    };
    /**
     * @example {
     *       "status": "DEGRADED",
     *       "checkedAt": "2026-08-05T10:30:00Z",
     *       "dependencies": [
     *         {
     *           "name": "seat-inventory-service",
     *           "critical": true,
     *           "status": "UP",
     *           "latencyMs": 12
     *         },
     *         {
     *           "name": "notification-service",
     *           "critical": false,
     *           "status": "DOWN",
     *           "latencyMs": 2000,
     *           "errorCode": "TIMEOUT"
     *         }
     *       ]
     *     }
     */
    AggregateHealth: {
      /** @enum {string} */
      status: 'UP' | 'DEGRADED' | 'DOWN';
      /** Format: date-time */
      checkedAt: string;
      dependencies: components['schemas']['DependencyHealth'][];
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
    /** @description Request violates validation or domain rules. */
    Unprocessable: {
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
    /** @description If-Match does not match the current ETag. */
    PreconditionFailed: {
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
  publicListEvents: {
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
      /** @description Thành công */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'][];
        };
      };
      500: components['responses']['InternalError'];
    };
  };
  publicGetEvent: {
    parameters: {
      query?: never;
      header?: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Thành công */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'];
        };
      };
      404: components['responses']['NotFound'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  placeBooking: {
    parameters: {
      query?: never;
      header: {
        /** @example idem-booking-12345678 */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
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
        'application/json': components['schemas']['PlaceBookingRequest'];
      };
    };
    responses: {
      /** @description Đặt vé thành công */
      201: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      /** @description Kết quả thanh toán chưa xác định; booking đang chờ đối soát. Client phải poll Location thay vì gửi lại lệnh đặt vé. */
      202: {
        headers: {
          /** @description Đường dẫn đọc trạng thái booking đang đối soát. */
          Location: string;
          /** @description Số giây tối thiểu trước lần poll kế tiếp. */
          'Retry-After': number;
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      /** @description Thanh toán bị từ chối */
      402: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ErrorResponse'];
        };
      };
      409: components['responses']['Conflict'];
      422: components['responses']['Unprocessable'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  publicGetBooking: {
    parameters: {
      query?: never;
      header?: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        bookingId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Thành công */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
    };
  };
  publicCancelBooking: {
    parameters: {
      query?: never;
      header: {
        /** @example idem-booking-12345678 */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
        /** @example "3" */
        'If-Match': components['parameters']['IfMatch'];
      };
      path: {
        bookingId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Đã hủy */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  aggregateHealth: {
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
      /** @description UP hoặc DEGRADED */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AggregateHealth'];
        };
      };
      /** @description DOWN vì ít nhất một dependency critical không phục vụ được. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AggregateHealth'];
        };
      };
    };
  };
  getWorkflowTrace: {
    parameters: {
      query?: never;
      header?: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        correlationId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Thành công */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TraceStep'][];
        };
      };
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
    };
  };
  issueRealtimeWebSocketTicket: {
    parameters: {
      query?: never;
      header: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
        /** @example idem-booking-12345678 */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['WsTicketRequest'];
      };
    };
    responses: {
      /** @description Signed single-use JWT/JWS ticket issued after an allowed Booking decision. */
      201: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          /**
           * @example {
           *       "ticket": "example-not-a-real-ticket",
           *       "bookingId": "BKG-001",
           *       "expiresAt": "2026-08-03T03:00:45Z"
           *     }
           */
          'application/json': components['schemas']['WsTicketResponse'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      /** @description Booking access denied; no ticket issued. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ErrorResponse'];
        };
      };
      /** @description WS ticket issuance rate limit exceeded. */
      429: {
        headers: {
          'Retry-After'?: number;
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ErrorResponse'];
        };
      };
      503: components['responses']['ServiceUnavailable'];
    };
  };
  esbLiveness: {
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
  esbReadiness: {
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
