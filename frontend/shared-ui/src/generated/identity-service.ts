// Generated from contracts/identity-service.yaml. Do not edit manually.
export interface paths {
  '/auth/register': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: operations['registerIdentityAccount'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/auth/login': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: operations['loginIdentityAccount'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/auth/refresh': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: operations['refreshIdentitySession'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/auth/logout': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post: operations['logoutIdentitySession'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/auth/me': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: operations['getCurrentIdentityPrincipal'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/admin/users/{userId}/roles': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** @description Assign or revoke a supported role. Requires ADMIN. */
    post: operations['changeIdentityUserRole'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/.well-known/jwks.json': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get: operations['getIdentityJwks'];
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
    get: operations['identityLiveness'];
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
    get: operations['identityReadiness'];
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
    ErrorDetail: {
      code: string;
      message: string;
      retryable: boolean;
      details: {
        [key: string]: unknown;
      };
    };
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
    RegisterRequest: {
      /** Format: email */
      email: string;
      /** Format: password */
      password: string;
    };
    LoginRequest: {
      /** Format: email */
      email: string;
      /** Format: password */
      password: string;
    };
    /** @enum {string} */
    Role: 'CUSTOMER' | 'ADMIN' | 'CHECKIN_STAFF' | 'SERVICE';
    RoleChangeRequest: {
      role: components['schemas']['Role'];
      /** @enum {string} */
      action: 'ASSIGN' | 'REVOKE';
    };
    User: {
      /** Format: uuid */
      userId: string;
      /** Format: email */
      email: string;
      /** @enum {string} */
      status: 'ACTIVE' | 'DISABLED';
      roles: components['schemas']['Role'][];
      tokenVersion: number;
      /** Format: date-time */
      createdAt: string;
    };
    /** @description Canonical access-token claims. customerId is intentionally absent and must never be treated as authoritative. */
    AccessTokenClaims: {
      sub: string;
      roles: components['schemas']['Role'][];
      tokenVersion: number;
      iss: string;
      aud: string | string[];
      iat: number;
      exp: number;
      nbf?: number;
      jti: string;
    };
    TokenResponse: {
      readonly accessToken: string;
      /** @constant */
      tokenType: 'Bearer';
      expiresIn: number;
      readonly csrfToken: string;
      user: components['schemas']['User'];
    };
    RoleChangeResponse: {
      user: components['schemas']['User'];
      role: components['schemas']['Role'];
      /** @enum {string} */
      action: 'ASSIGN' | 'REVOKE';
      changed: boolean;
    };
    JwkSet: {
      keys: {
        /** @constant */
        kty: 'RSA';
        /** @constant */
        use: 'sig';
        /** @constant */
        alg: 'RS256';
        kid: string;
        n: string;
        e: string;
      }[];
    };
    Health: {
      /** @constant */
      service: 'identity-service';
      /** @enum {string} */
      status: 'UP' | 'READY' | 'DRAINING' | 'NOT_READY';
      version: string;
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
    /** @description Account is temporarily locked. */
    Locked: {
      headers: {
        'Retry-After'?: number;
        'X-Correlation-ID': components['headers']['CorrelationId'];
        'X-Trace-ID': components['headers']['TraceId'];
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
    /** @description Authentication rate limit exceeded. */
    RateLimited: {
      headers: {
        'Retry-After'?: number;
        'X-Correlation-ID': components['headers']['CorrelationId'];
        'X-Trace-ID': components['headers']['TraceId'];
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Request body exceeds the allowed size. */
    PayloadTooLarge: {
      headers: {
        'X-Correlation-ID': components['headers']['CorrelationId'];
        'X-Trace-ID': components['headers']['TraceId'];
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
    /** @description Unexpected server failure. */
    InternalError: {
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
  };
  parameters: {
    UserId: string;
    CsrfHeader: string;
    /** @example corr-1234567890abcdef */
    CorrelationId: string;
    /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
    Traceparent: string;
    /** @description Double-submit CSRF cookie. Must equal X-CSRF-Token. */
    CsrfCookie: string;
    /** @example idem-booking-12345678 */
    IdempotencyKey: string;
    /** @example "3" */
    IfMatch: string;
  };
  requestBodies: never;
  headers: {
    /** @description Request correlation identifier used across logs and services. */
    CorrelationId: string;
    /** @description Server trace identifier for diagnostics. */
    TraceId: string;
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
  registerIdentityAccount: {
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
        'application/json': components['schemas']['RegisterRequest'];
      };
    };
    responses: {
      /** @description Account registered. */
      201: {
        headers: {
          'X-Correlation-ID': components['headers']['CorrelationId'];
          'X-Trace-ID': components['headers']['TraceId'];
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['User'];
        };
      };
      400: components['responses']['BadRequest'];
      409: components['responses']['Conflict'];
      413: components['responses']['PayloadTooLarge'];
      422: components['responses']['Unprocessable'];
      500: components['responses']['InternalError'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  loginIdentityAccount: {
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
        'application/json': components['schemas']['LoginRequest'];
      };
    };
    responses: {
      /** @description Access JWT and refresh-session metadata. */
      200: {
        headers: {
          'Cache-Control'?: 'no-store';
          Pragma?: 'no-cache';
          'X-Correlation-ID': components['headers']['CorrelationId'];
          'X-Trace-ID': components['headers']['TraceId'];
          /** @description Sets identity_refresh (HttpOnly) and identity_csrf cookies for the local browser session. */
          'Set-Cookie'?: string;
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TokenResponse'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      413: components['responses']['PayloadTooLarge'];
      422: components['responses']['Unprocessable'];
      423: components['responses']['Locked'];
      429: components['responses']['RateLimited'];
      500: components['responses']['InternalError'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  refreshIdentitySession: {
    parameters: {
      query?: never;
      header: {
        'X-CSRF-Token': components['parameters']['CsrfHeader'];
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie: {
        /** @description Double-submit CSRF cookie. Must equal X-CSRF-Token. */
        identity_csrf: components['parameters']['CsrfCookie'];
      };
    };
    requestBody?: never;
    responses: {
      /** @description Refresh token rotated and a new access JWT issued. */
      200: {
        headers: {
          'Cache-Control'?: 'no-store';
          Pragma?: 'no-cache';
          'X-Correlation-ID': components['headers']['CorrelationId'];
          'X-Trace-ID': components['headers']['TraceId'];
          /** @description Rotates identity_refresh and identity_csrf cookies. Previous refresh token is consumed. */
          'Set-Cookie'?: string;
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TokenResponse'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      500: components['responses']['InternalError'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  logoutIdentitySession: {
    parameters: {
      query?: never;
      header: {
        'X-CSRF-Token': components['parameters']['CsrfHeader'];
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie: {
        /** @description Double-submit CSRF cookie. Must equal X-CSRF-Token. */
        identity_csrf: components['parameters']['CsrfCookie'];
      };
    };
    requestBody?: never;
    responses: {
      /** @description Refresh-token family revoked or already absent. */
      204: {
        headers: {
          'X-Correlation-ID': components['headers']['CorrelationId'];
          'X-Trace-ID': components['headers']['TraceId'];
          /** @description Expires identity_refresh and identity_csrf cookies. */
          'Set-Cookie'?: string;
          [name: string]: unknown;
        };
        content?: never;
      };
      403: components['responses']['Forbidden'];
      500: components['responses']['InternalError'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  getCurrentIdentityPrincipal: {
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
      /** @description Current Identity account and roles. */
      200: {
        headers: {
          'X-Correlation-ID': components['headers']['CorrelationId'];
          'X-Trace-ID': components['headers']['TraceId'];
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['User'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      500: components['responses']['InternalError'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  changeIdentityUserRole: {
    parameters: {
      query?: never;
      header: {
        /** @example corr-1234567890abcdef */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /** @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 */
        traceparent?: components['parameters']['Traceparent'];
        /** @example idem-booking-12345678 */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /** @example "3" */
        'If-Match': components['parameters']['IfMatch'];
      };
      path: {
        userId: components['parameters']['UserId'];
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['RoleChangeRequest'];
      };
    };
    responses: {
      /** @description Role mutation result. */
      200: {
        headers: {
          'X-Correlation-ID': components['headers']['CorrelationId'];
          'X-Trace-ID': components['headers']['TraceId'];
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['RoleChangeResponse'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      412: components['responses']['PreconditionFailed'];
      413: components['responses']['PayloadTooLarge'];
      422: components['responses']['Unprocessable'];
      500: components['responses']['InternalError'];
      503: components['responses']['ServiceUnavailable'];
    };
  };
  getIdentityJwks: {
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
      /** @description Public JSON Web Key Set for access JWT verification. */
      200: {
        headers: {
          'Cache-Control'?: string;
          'X-Correlation-ID': components['headers']['CorrelationId'];
          'X-Trace-ID': components['headers']['TraceId'];
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/jwk-set+json': components['schemas']['JwkSet'];
        };
      };
      500: components['responses']['InternalError'];
    };
  };
  identityLiveness: {
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
  identityReadiness: {
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
