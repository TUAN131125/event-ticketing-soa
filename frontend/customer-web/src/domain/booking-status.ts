import type { BookingStatus } from '@event-ticketing/shared-ui/frontend-esb-contract';

/** Public booking states are generated from the canonical ESB contract. */
export type KnownBookingStatus = BookingStatus;

const KNOWN_STATUSES: readonly KnownBookingStatus[] = [
  'PENDING',
  'SEAT_RESERVED',
  'PAYMENT_PROCESSING',
  'CONFIRMED',
  'FAILED',
  'CANCELLED',
  'COMPENSATION_PENDING',
];

export function isKnownBookingStatus(status: string): status is KnownBookingStatus {
  return (KNOWN_STATUSES as readonly string[]).includes(status);
}

/** Terminal statuses: no further automatic polling is useful. */
export function isSettled(status: string): boolean {
  return status === 'CONFIRMED' || status === 'FAILED' || status === 'CANCELLED';
}

export function isConfirmed(status: string): boolean {
  return status === 'CONFIRMED';
}

export function isUnsuccessful(status: string): boolean {
  return status === 'FAILED' || status === 'CANCELLED';
}

/**
 * PAYMENT_PROCESSING is also used while Payment Service reconciliation owns an
 * unknown provider outcome. The browser must poll; it must never resend the command.
 */
export function isReconciling(status: string): boolean {
  return status === 'PAYMENT_PROCESSING' || status === 'COMPENSATION_PENDING';
}

export type StatusTone = 'success' | 'warning' | 'danger' | 'information' | 'neutral';

export interface BookingStatusView {
  label: string;
  tone: StatusTone;
  description: string;
  inProgress: boolean;
}

export function describeBookingStatus(status: string): BookingStatusView {
  switch (status) {
    case 'PENDING':
      return {
        label: 'Pending',
        tone: 'information',
        description: 'The booking has been accepted and the workflow has started.',
        inProgress: true,
      };
    case 'SEAT_RESERVED':
      return {
        label: 'Seat reserved',
        tone: 'information',
        description: 'Your seats are held while the payment is processed.',
        inProgress: true,
      };
    case 'PAYMENT_PROCESSING':
      return {
        label: 'Payment processing',
        tone: 'warning',
        description:
          'The payment result is being verified. This page reloads the authoritative status; do not submit the booking again.',
        inProgress: true,
      };
    case 'COMPENSATION_PENDING':
      return {
        label: 'Compensation pending',
        tone: 'warning',
        description:
          'The workflow is undoing an incomplete step. No further action is needed from you.',
        inProgress: true,
      };
    case 'CONFIRMED':
      return {
        label: 'Confirmed',
        tone: 'success',
        description: 'The booking is confirmed and the tickets have been issued.',
        inProgress: false,
      };
    case 'FAILED':
      return {
        label: 'Failed',
        tone: 'danger',
        description: 'The booking did not complete. Compensation status remains authoritative.',
        inProgress: false,
      };
    case 'CANCELLED':
      return {
        label: 'Cancelled',
        tone: 'danger',
        description: 'The booking was cancelled.',
        inProgress: false,
      };
    default:
      return {
        label: status || 'Unknown',
        tone: 'neutral',
        description:
          'This status is not recognised by this browser build. Reload the authoritative booking state.',
        inProgress: false,
      };
  }
}
