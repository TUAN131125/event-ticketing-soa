// Generated from contracts/esb-public-api.yaml. Do not edit manually.
// Contract SHA-256: b637be85428c8d99b74116dc9ba6b06b6fd1442667840172a035753a80347255
export interface paths {
  '/api/auth/register': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Auth Register */
    post: operations['registerIdentityAccountViaEsb'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/auth/login': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Auth Login */
    post: operations['loginIdentityAccountViaEsb'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/auth/refresh': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Auth Refresh */
    post: operations['refreshIdentitySessionViaEsb'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/auth/logout': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Auth Logout */
    post: operations['logoutIdentitySessionViaEsb'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/auth/me': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Auth Me */
    get: operations['getCurrentIdentityPrincipalViaEsb'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/events': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Events */
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
    /** Get Event */
    get: operations['publicGetEvent'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/events/{eventId}/seat-map': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Seat Map */
    get: operations['publicGetEventSeatMap'];
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
    /** List Bookings */
    get: operations['publicListBookings'];
    put?: never;
    /** Place Booking */
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
    /** Get Booking */
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
    /** Cancel Booking */
    post: operations['publicCancelBooking'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/bookings/{bookingId}/tickets': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Booking Tickets */
    get: operations['publicListBookingTickets'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/tickets': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Tickets */
    get: operations['publicListTickets'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/tickets/{ticketId}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Ticket */
    get: operations['publicGetTicket'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/me/customer': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get My Customer */
    get: operations['getMyCustomerProfile'];
    /** Upsert My Customer */
    put: operations['upsertMyCustomerProfile'];
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/me/customer/consents': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Update My Customer Consent */
    post: operations['updateMyCustomerConsent'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/admin/events': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Admin Create Event */
    post: operations['adminCreateEvent'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/admin/events/{eventId}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    /** Admin Replace Event */
    put: operations['adminReplaceEvent'];
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/admin/events/{eventId}/publish': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Admin Publish Event */
    post: operations['adminPublishEvent'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/admin/events/{eventId}/pause': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Admin Pause Event */
    post: operations['adminPauseEvent'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/admin/events/{eventId}/close': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Admin Close Event */
    post: operations['adminCloseEvent'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/admin/events/{eventId}/cancel': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Admin Cancel Event */
    post: operations['adminCancelEvent'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/admin/events/{eventId}/seat-inventory': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Admin Get Seat Inventory */
    get: operations['adminGetSeatInventory'];
    /** Admin Configure Seat Inventory */
    put: operations['adminConfigureSeatInventory'];
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/check-in/validate': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Validate Ticket */
    post: operations['validateTicketForCheckIn'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/check-in/tickets/{ticketId}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Checkin */
    post: operations['checkInTicketViaEsb'];
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
    /** Realtime Ticket */
    post: operations['issueRealtimeWebSocketTicket'];
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
    /** Trace */
    get: operations['getWorkflowTrace'];
    put?: never;
    post?: never;
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
    /** Health */
    get: operations['aggregateHealth'];
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
    /** Live */
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
    /** Ready */
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
    /** AdminSeatDefinition */
    AdminSeatDefinition: {
      /** Seatid */
      seatId: string;
      /** Section */
      section: string;
      /** Rowlabel */
      rowLabel: string;
      /** Seatnumber */
      seatNumber: string;
      /** Tickettypeid */
      ticketTypeId: string;
      /**
       * Status
       * @default AVAILABLE
       * @enum {string}
       */
      status: 'AVAILABLE' | 'BLOCKED';
    };
    /** AdminSeatInventoryProjection */
    AdminSeatInventoryProjection: {
      /** Eventid */
      eventId: string;
      /**
       * Generatedat
       * Format: date-time
       */
      generatedAt: string;
      /** Seats */
      seats: components['schemas']['SeatProjection'][];
    };
    /** AdminTicketTypeInput */
    AdminTicketTypeInput: {
      /** Tickettypeid */
      ticketTypeId: string;
      /** Name */
      name: string;
      price: components['schemas']['MoneyRequest'];
    };
    /** AggregateHealth */
    AggregateHealth: {
      /**
       * Status
       * @enum {string}
       */
      status: 'UP' | 'DEGRADED' | 'DOWN';
      /**
       * Checkedat
       * Format: date-time
       */
      checkedAt: string;
      /** Dependencies */
      dependencies: components['schemas']['DependencyHealth'][];
    };
    /**
     * AuthRole
     * @enum {string}
     */
    AuthRole: 'CUSTOMER' | 'ADMIN' | 'CHECKIN_STAFF' | 'SERVICE';
    /** BookingListProjection */
    BookingListProjection: {
      /** Items */
      items: components['schemas']['BookingResult'][];
      /** Page */
      page: number;
      /** Pagesize */
      pageSize: number;
      /** Totalitems */
      totalItems: number;
    };
    /**
     * BookingPaymentStatus
     * @enum {string}
     */
    BookingPaymentStatus:
      'PENDING' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN' | 'REFUND_PENDING' | 'REFUNDED';
    /** BookingResult */
    BookingResult: {
      /** Bookingid */
      bookingId: string;
      /** Eventid */
      eventId: string;
      /** Seatids */
      seatIds: string[];
      status: components['schemas']['BookingStatus'];
      total: components['schemas']['Money'];
      /** Reservationid */
      reservationId?: string | null;
      /** Paymentid */
      paymentId?: string | null;
      /** Ticketids */
      ticketIds: string[];
      /** Correlationid */
      correlationId: string;
      paymentStatus?: components['schemas']['BookingPaymentStatus'] | null;
      /** Workflowid */
      workflowId?: string | null;
      /** Resourceversion */
      resourceVersion: number;
      /** Createdat */
      createdAt?: string | null;
      /** Updatedat */
      updatedAt?: string | null;
    };
    /**
     * BookingStatus
     * @enum {string}
     */
    BookingStatus:
      | 'PENDING'
      | 'SEAT_RESERVED'
      | 'PAYMENT_PROCESSING'
      | 'CONFIRMED'
      | 'FAILED'
      | 'CANCELLED'
      | 'COMPENSATION_PENDING';
    /** CancelBookingRequest */
    CancelBookingRequest: {
      /**
       * Reason
       * @default USER_REQUEST
       */
      reason: string;
    };
    /** CheckInRequest */
    CheckInRequest: {
      /** Qrtoken */
      qrToken: string;
    };
    /** CheckInResult */
    CheckInResult: {
      ticket: components['schemas']['TicketProjection'];
      /** Correlationid */
      correlationId: string;
    };
    /** CheckInValidateRequest */
    CheckInValidateRequest: {
      /** Qrtoken */
      qrToken: string;
    };
    /** ConfigureSeatInventoryRequest */
    ConfigureSeatInventoryRequest: {
      /** Inventoryversion */
      inventoryVersion: number;
      /** Seats */
      seats: components['schemas']['AdminSeatDefinition'][];
    };
    /** ConfigureSeatInventoryResult */
    ConfigureSeatInventoryResult: {
      /** Eventid */
      eventId: string;
      /** Inventoryversion */
      inventoryVersion: number;
      /** Configuredseatcount */
      configuredSeatCount: number;
      /**
       * Status
       * @enum {string}
       */
      status: 'CONFIGURED' | 'REPLAYED';
    };
    /** ConsentUpdateRequest */
    ConsentUpdateRequest: {
      /**
       * Channel
       * @enum {string}
       */
      channel: 'EMAIL' | 'SMS';
      /** Granted */
      granted: boolean;
    };
    /** ConsentUpdateResult */
    ConsentUpdateResult: {
      /** Customerid */
      customerId: string;
      /**
       * Channel
       * @enum {string}
       */
      channel: 'EMAIL' | 'SMS';
      /** Granted */
      granted: boolean;
      /** Resourceversion */
      resourceVersion: number;
    };
    /** CustomerProfileInput */
    CustomerProfileInput: {
      /** Fullname */
      fullName: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      /** Phone */
      phone?: string | null;
    };
    /** CustomerProfileProjection */
    CustomerProfileProjection: {
      /** Customerid */
      customerId: string;
      /** Fullname */
      fullName: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      /** Phone */
      phone?: string | null;
      /**
       * Status
       * @enum {string}
       */
      status: 'ACTIVE' | 'INACTIVE' | 'ANONYMIZED';
      /** Resourceversion */
      resourceVersion: number;
      /**
       * Createdat
       * Format: date-time
       */
      createdAt: string;
      /**
       * Updatedat
       * Format: date-time
       */
      updatedAt: string;
    };
    /** DependencyHealth */
    DependencyHealth: {
      /** Name */
      name: string;
      /** Critical */
      critical: boolean;
      /**
       * Status
       * @enum {string}
       */
      status: 'UP' | 'DOWN';
      /** Latencyms */
      latencyMs?: number | null;
      /** Errorcode */
      errorCode?: ('TIMEOUT' | 'UNREACHABLE' | 'NOT_READY') | null;
    };
    /**
     * ErrorResponse
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
      /** Correlationid */
      correlationId: string;
      /** Traceid */
      traceId?: string | null;
      /** ErrorBody */
      error: {
        /** Code */
        code: string;
        /** Message */
        message: string;
        /** Retryable */
        retryable: boolean;
        /** Details */
        details?: {
          [key: string]: unknown;
        } | null;
      };
    };
    /**
     * EventAdminRequest
     * @description Transport validation only. Event Service remains domain authority.
     */
    EventAdminRequest: {
      /** Name */
      name: string;
      /** Venue */
      venue: string;
      /** Startsat */
      startsAt: string;
      /** Salestartsat */
      saleStartsAt: string;
      /** Saleendsat */
      saleEndsAt: string;
      /** Tickettypes */
      ticketTypes: components['schemas']['AdminTicketTypeInput'][];
    };
    /**
     * EventStatus
     * @enum {string}
     */
    EventStatus: 'DRAFT' | 'ON_SALE' | 'PAUSED' | 'CANCELLED' | 'ENDED';
    /**
     * HealthStatus
     * @example {
     *       "status": "READY",
     *       "service": "booking-orchestrator",
     *       "version": "2.2.0"
     *     }
     */
    HealthStatus: {
      /**
       * Status
       * @enum {string}
       */
      status: 'UP' | 'READY' | 'NOT_READY';
      /** Service */
      service?: string | null;
      /** Version */
      version?: string | null;
    };
    /** LoginRequest */
    LoginRequest: {
      /**
       * Email
       * Format: email
       */
      email: string;
      /** Password */
      password: string;
    };
    /**
     * Money
     * @example {
     *       "amountMinor": 250000,
     *       "currency": "VND"
     *     }
     */
    Money: {
      /** Amountminor */
      amountMinor: number;
      /** Currency */
      currency: string;
    };
    /** MoneyRequest */
    MoneyRequest: {
      /** Amountminor */
      amountMinor: number;
      /** Currency */
      currency: string;
    };
    /** PlaceBookingRequest */
    PlaceBookingRequest: {
      /**
       * Customerid
       * @deprecated
       * @description Compatibility only. ESB resolves ownership from the authenticated identity.
       */
      customerId?: string | null;
      /** Eventid */
      eventId: string;
      /** Seatids */
      seatIds: string[];
      /** Paymentmethodtoken */
      paymentMethodToken: string;
    };
    /** PublicEvent */
    PublicEvent: {
      /** Eventid */
      eventId: string;
      /** Name */
      name: string;
      /** Venue */
      venue: string;
      /**
       * Startsat
       * Format: date-time
       */
      startsAt: string;
      /** Salestartsat */
      saleStartsAt?: string | null;
      /** Saleendsat */
      saleEndsAt?: string | null;
      status: components['schemas']['EventStatus'];
      /** Tickettypes */
      ticketTypes: components['schemas']['TicketTypeProjection'][];
      /** Resourceversion */
      resourceVersion: number;
    };
    /** RegisterRequest */
    RegisterRequest: {
      /**
       * Email
       * Format: email
       */
      email: string;
      /** Password */
      password: string;
    };
    /**
     * SeatAvailability
     * @enum {string}
     */
    SeatAvailability: 'AVAILABLE' | 'UNAVAILABLE';
    /** SeatMapProjection */
    SeatMapProjection: {
      /** Eventid */
      eventId: string;
      /**
       * Generatedat
       * Format: date-time
       */
      generatedAt: string;
      /** Seats */
      seats: components['schemas']['SeatProjection'][];
    };
    /** SeatProjection */
    SeatProjection: {
      /** Seatid */
      seatId: string;
      /** Seatcode */
      seatCode: string;
      /** Section */
      section?: string | null;
      /** Row */
      row?: string | null;
      /** Tickettypeid */
      ticketTypeId: string;
      /** Tickettypename */
      ticketTypeName: string;
      status: components['schemas']['SeatAvailability'];
      price: components['schemas']['Money'];
    };
    /** TicketListProjection */
    TicketListProjection: {
      /** Items */
      items: components['schemas']['TicketProjection'][];
      /** Page */
      page: number;
      /** Pagesize */
      pageSize: number;
      /** Totalitems */
      totalItems: number;
    };
    /** TicketProjection */
    TicketProjection: {
      /** Ticketid */
      ticketId: string;
      /** Bookingid */
      bookingId: string;
      /** Eventid */
      eventId: string;
      /** Eventname */
      eventName: string;
      /** Venue */
      venue: string;
      /** Startsat */
      startsAt: string;
      /** Seatid */
      seatId: string;
      /** Seatcode */
      seatCode: string;
      /** Tickettypename */
      ticketTypeName: string;
      status: components['schemas']['TicketStatus'];
      /**
       * Qrtoken
       * @description Owner-only secret. Never log or persist in browser storage.
       */
      qrToken?: string | null;
      /** Correlationid */
      correlationId: string;
      /** Resourceversion */
      resourceVersion: number;
    };
    /**
     * TicketStatus
     * @enum {string}
     */
    TicketStatus: 'ISSUED' | 'CHECKED_IN' | 'CANCELLED';
    /** TicketTypeProjection */
    TicketTypeProjection: {
      /** Tickettypeid */
      ticketTypeId: string;
      /** Name */
      name: string;
      price: components['schemas']['Money'];
    };
    /** TicketValidationResult */
    TicketValidationResult: {
      /** Valid */
      valid: boolean;
      ticket?: components['schemas']['TicketProjection'] | null;
      /** Code */
      code?: string | null;
      /** Message */
      message?: string | null;
      /** Correlationid */
      correlationId: string;
    };
    /** TokenResponse */
    TokenResponse: {
      /** Accesstoken */
      accessToken: string;
      /**
       * Tokentype
       * @constant
       */
      tokenType: 'Bearer';
      /** Expiresin */
      expiresIn: number;
      /** Csrftoken */
      csrfToken: string;
      user: components['schemas']['User'];
    };
    /** TraceStep */
    TraceStep: {
      /** Service */
      service: string;
      /** Operation */
      operation: string;
      /** Status */
      status: string;
      /** Durationms */
      durationMs: number;
      /** Errorcode */
      errorCode?: string | null;
    };
    /** User */
    User: {
      /** Userid */
      userId: string;
      /**
       * Email
       * Format: email
       */
      email: string;
      /**
       * Status
       * @enum {string}
       */
      status: 'ACTIVE' | 'DISABLED';
      /** Roles */
      roles: components['schemas']['AuthRole'][];
      /** Tokenversion */
      tokenVersion: number;
      /**
       * Createdat
       * Format: date-time
       */
      createdAt: string;
    };
    /** WsTicketRequest */
    WsTicketRequest: {
      /** Bookingid */
      bookingId: string;
    };
    /** WsTicketResponse */
    WsTicketResponse: {
      /** Ticket */
      ticket: string;
      /** Bookingid */
      bookingId: string;
      /**
       * Expiresat
       * Format: date-time
       */
      expiresAt: string;
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
    /** @description Payment was declined. */
    PaymentDeclined: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Not authorized. */
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
    /** @description State, uniqueness or idempotency conflict. */
    Conflict: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description If-Match does not match the resource version. */
    PreconditionFailed: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Request payload is too large. */
    PayloadTooLarge: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Validation or domain-rule rejection. */
    Unprocessable: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Identity account is temporarily locked. */
    AccountLocked: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Rate limit exceeded. */
    RateLimited: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Unexpected gateway failure. */
    InternalError: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Provider returned an invalid response. */
    BadGateway: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Required dependency is unavailable. */
    ServiceUnavailable: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
    /** @description Request deadline exceeded. */
    GatewayTimeout: {
      headers: {
        [name: string]: unknown;
      };
      content: {
        'application/json': components['schemas']['ErrorResponse'];
      };
    };
  };
  parameters: {
    /**
     * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
     * @example corr-1234567890abcdef
     */
    CorrelationId: string;
    /** @description Correlation id that the caller must supply. */
    RequiredCorrelationId: string;
    /**
     * @description W3C trace context. A new trace id is created when absent or malformed.
     * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
     */
    Traceparent: string;
    /**
     * @description Client-generated key that makes a retried command safe to replay.
     * @example idem-booking-12345678
     */
    IdempotencyKey: string;
    /**
     * @description Resource version the command expects, taken from the last ETag.
     * @example "3"
     */
    IfMatch: string;
    /**
     * @description Resource version the command expects. Optional because the operation also creates the resource when it does not exist yet; when omitted the gateway uses the version it just read.
     * @example "3"
     */
    OptionalIfMatch: string;
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
  registerIdentityAccountViaEsb: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
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
      /** @description Successful Response */
      201: {
        headers: {
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
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  loginIdentityAccountViaEsb: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
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
      /** @description Successful Response */
      200: {
        headers: {
          /** @description Identity refresh and CSRF cookies. Multiple Set-Cookie header fields may be returned; the ESB preserves HttpOnly, Secure and SameSite attributes and rewrites Path to /api/auth. */
          'Set-Cookie'?: string;
          /** @description Authentication responses are not cacheable. */
          'Cache-Control'?: string;
          /** @description Legacy no-cache directive preserved from Identity. */
          Pragma?: string;
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TokenResponse'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      422: components['responses']['Unprocessable'];
      423: components['responses']['AccountLocked'];
      429: components['responses']['RateLimited'];
      500: components['responses']['InternalError'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  refreshIdentitySessionViaEsb: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          /** @description Identity refresh and CSRF cookies. Multiple Set-Cookie header fields may be returned; the ESB preserves HttpOnly, Secure and SameSite attributes and rewrites Path to /api/auth. */
          'Set-Cookie'?: string;
          /** @description Authentication responses are not cacheable. */
          'Cache-Control'?: string;
          /** @description Legacy no-cache directive preserved from Identity. */
          Pragma?: string;
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TokenResponse'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      422: components['responses']['Unprocessable'];
      500: components['responses']['InternalError'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  logoutIdentitySessionViaEsb: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          /** @description Identity refresh and CSRF cookies. Multiple Set-Cookie header fields may be returned; the ESB preserves HttpOnly, Secure and SameSite attributes and rewrites Path to /api/auth. */
          'Set-Cookie'?: string;
          /** @description Authentication responses are not cacheable. */
          'Cache-Control'?: string;
          /** @description Legacy no-cache directive preserved from Identity. */
          Pragma?: string;
          [name: string]: unknown;
        };
        content?: never;
      };
      403: components['responses']['Forbidden'];
      422: components['responses']['Unprocessable'];
      500: components['responses']['InternalError'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  getCurrentIdentityPrincipalViaEsb: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['User'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      422: components['responses']['Unprocessable'];
      500: components['responses']['InternalError'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicListEvents: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'][];
        };
      };
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicGetEvent: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
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
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicGetEventSeatMap: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['SeatMapProjection'];
        };
      };
      404: components['responses']['NotFound'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicListBookings: {
    parameters: {
      query?: {
        status?: components['schemas']['BookingStatus'] | null;
        page?: number;
        pageSize?: number;
      };
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingListProjection'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  placeBooking: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
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
      /** @description Successful Response */
      201: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      /** @description Booking is reconciling. */
      202: {
        headers: {
          ETag: components['headers']['ETag'];
          Location?: string;
          'Retry-After'?: string;
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      402: components['responses']['PaymentDeclined'];
      409: components['responses']['Conflict'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicGetBooking: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        bookingId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicCancelBooking: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects, taken from the last ETag.
         * @example "3"
         */
        'If-Match': components['parameters']['IfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        bookingId: string;
      };
      cookie?: never;
    };
    requestBody?: {
      content: {
        'application/json': components['schemas']['CancelBookingRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['BookingResult'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicListBookingTickets: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        bookingId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TicketProjection'][];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicListTickets: {
    parameters: {
      query?: {
        page?: number;
        pageSize?: number;
      };
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TicketListProjection'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  publicGetTicket: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        ticketId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TicketProjection'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  getMyCustomerProfile: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CustomerProfileProjection'];
        };
      };
      401: components['responses']['Unauthorized'];
      404: components['responses']['NotFound'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  upsertMyCustomerProfile: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects. Optional because the operation also creates the resource when it does not exist yet; when omitted the gateway uses the version it just read.
         * @example "3"
         */
        'If-Match'?: components['parameters']['OptionalIfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['CustomerProfileInput'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CustomerProfileProjection'];
        };
      };
      /** @description Created */
      201: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CustomerProfileProjection'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  updateMyCustomerConsent: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects. Optional because the operation also creates the resource when it does not exist yet; when omitted the gateway uses the version it just read.
         * @example "3"
         */
        'If-Match'?: components['parameters']['OptionalIfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['ConsentUpdateRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ConsentUpdateResult'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminCreateEvent: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['EventAdminRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      409: components['responses']['Conflict'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminReplaceEvent: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects, taken from the last ETag.
         * @example "3"
         */
        'If-Match': components['parameters']['IfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['EventAdminRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminPublishEvent: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects, taken from the last ETag.
         * @example "3"
         */
        'If-Match': components['parameters']['IfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminPauseEvent: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects, taken from the last ETag.
         * @example "3"
         */
        'If-Match': components['parameters']['IfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminCloseEvent: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects, taken from the last ETag.
         * @example "3"
         */
        'If-Match': components['parameters']['IfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminCancelEvent: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects, taken from the last ETag.
         * @example "3"
         */
        'If-Match': components['parameters']['IfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PublicEvent'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminGetSeatInventory: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AdminSeatInventoryProjection'];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  adminConfigureSeatInventory: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        eventId: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['ConfigureSeatInventoryRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ConfigureSeatInventoryResult'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      422: components['responses']['Unprocessable'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  validateTicketForCheckIn: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['CheckInValidateRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TicketValidationResult'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      409: components['responses']['Conflict'];
      422: components['responses']['Unprocessable'];
      429: components['responses']['RateLimited'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  checkInTicketViaEsb: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Resource version the command expects, taken from the last ETag.
         * @example "3"
         */
        'If-Match': components['parameters']['IfMatch'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        ticketId: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['CheckInRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          ETag: components['headers']['ETag'];
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CheckInResult'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      412: components['responses']['PreconditionFailed'];
      422: components['responses']['Unprocessable'];
      429: components['responses']['RateLimited'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  issueRealtimeWebSocketTicket: {
    parameters: {
      query?: never;
      header: {
        /**
         * @description Client-generated key that makes a retried command safe to replay.
         * @example idem-booking-12345678
         */
        'Idempotency-Key': components['parameters']['IdempotencyKey'];
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
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
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['WsTicketResponse'];
        };
      };
      400: components['responses']['BadRequest'];
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      409: components['responses']['Conflict'];
      422: components['responses']['Unprocessable'];
      429: components['responses']['RateLimited'];
      502: components['responses']['BadGateway'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  getWorkflowTrace: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path: {
        correlationId: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TraceStep'][];
        };
      };
      401: components['responses']['Unauthorized'];
      403: components['responses']['Forbidden'];
      404: components['responses']['NotFound'];
      422: components['responses']['Unprocessable'];
      503: components['responses']['ServiceUnavailable'];
      504: components['responses']['GatewayTimeout'];
    };
  };
  aggregateHealth: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AggregateHealth'];
        };
      };
      /** @description One or more critical dependencies are unavailable. */
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
  esbLiveness: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
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
  esbReadiness: {
    parameters: {
      query?: never;
      header?: {
        /**
         * @description Caller-supplied correlation id, echoed on the response. The gateway generates one when the header is absent.
         * @example corr-1234567890abcdef
         */
        'X-Correlation-ID'?: components['parameters']['CorrelationId'];
        /**
         * @description W3C trace context. A new trace id is created when absent or malformed.
         * @example 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
         */
        traceparent?: components['parameters']['Traceparent'];
      };
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HealthStatus'];
        };
      };
      /** @description Service is not ready. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HealthStatus'];
        };
      };
    };
  };
}
