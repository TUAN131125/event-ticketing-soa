import type { components, operations } from './generated/esb-public-api';

/**
 * Frontend aliases over operation request/response types generated from the
 * canonical ESB OpenAPI. Wire shapes must not be transcribed by hand.
 */
export type PublicEventList =
  operations['publicListEvents']['responses'][200]['content']['application/json'];
export type PublicEvent =
  operations['publicGetEvent']['responses'][200]['content']['application/json'];
export type SeatMapProjection =
  operations['publicGetEventSeatMap']['responses'][200]['content']['application/json'];
export type PlaceBookingRequest =
  operations['placeBooking']['requestBody']['content']['application/json'];
export type BookingResult =
  operations['publicGetBooking']['responses'][200]['content']['application/json'];
export type BookingListProjection =
  operations['publicListBookings']['responses'][200]['content']['application/json'];
export type CancelBookingRequest = NonNullable<
  operations['publicCancelBooking']['requestBody']
>['content']['application/json'];
export type TicketProjection =
  operations['publicGetTicket']['responses'][200]['content']['application/json'];
export type TicketListProjection =
  operations['publicListTickets']['responses'][200]['content']['application/json'];
export type AdminEventInput =
  operations['adminCreateEvent']['requestBody']['content']['application/json'];
export type AdminEventProjection =
  operations['adminCreateEvent']['responses'][201]['content']['application/json'];
export type TicketValidationRequest =
  operations['validateTicketForCheckIn']['requestBody']['content']['application/json'];
export type TicketValidationResult =
  operations['validateTicketForCheckIn']['responses'][200]['content']['application/json'];
export type CheckInRequest =
  operations['checkInTicket']['requestBody']['content']['application/json'];
export type CheckInResult =
  operations['checkInTicket']['responses'][200]['content']['application/json'];
export type RealtimeWsTicketRequest =
  operations['issueRealtimeWebSocketTicket']['requestBody']['content']['application/json'];
export type RealtimeWsTicket =
  operations['issueRealtimeWebSocketTicket']['responses'][201]['content']['application/json'];
export type AggregateHealth =
  operations['aggregateHealth']['responses'][200]['content']['application/json'];
export type TraceSteps =
  operations['getWorkflowTrace']['responses'][200]['content']['application/json'];

export type CustomerProfileInput =
  operations['upsertMyCustomerProfile']['requestBody']['content']['application/json'];
export type CustomerProfileProjection =
  operations['getMyCustomerProfile']['responses'][200]['content']['application/json'];
export type ConsentUpdateRequest =
  operations['updateMyCustomerConsent']['requestBody']['content']['application/json'];
export type ConsentUpdateResult =
  operations['updateMyCustomerConsent']['responses'][200]['content']['application/json'];
export type AdminSeatInventoryProjection =
  operations['adminGetSeatInventory']['responses'][200]['content']['application/json'];
export type ConfigureSeatInventoryRequest =
  operations['adminConfigureSeatInventory']['requestBody']['content']['application/json'];
export type ConfigureSeatInventoryResult =
  operations['adminConfigureSeatInventory']['responses'][200]['content']['application/json'];

export type MoneyProjection = components['schemas']['Money'];
export type SeatAvailability = components['schemas']['SeatProjection']['status'];
export type SeatProjection = components['schemas']['SeatProjection'];
export type BookingStatus = components['schemas']['BookingStatus'];
export type BookingPaymentStatus = components['schemas']['BookingPaymentStatus'];
export type TicketStatus = components['schemas']['TicketProjection']['status'];
export type AdminTicketTypeInput = components['schemas']['AdminTicketTypeInput'];

/** UI-04 is a client-side validated checkout draft, not an ESB wire contract. */
export type CustomerContactDraft = {
  fullName: string;
  email: string;
  phone: string;
};
