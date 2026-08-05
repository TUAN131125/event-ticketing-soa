import type { components } from '@event-ticketing/shared-ui/realtime-messages';

/**
 * `BookingResult.status` is an open string in contracts/esb-public-api.yaml. The known
 * values are the ones the Realtime projection enumerates; anything else must degrade to a
 * safe, non-committal presentation rather than being guessed at.
 */
export type KnownBookingStatus = components['schemas']['RealtimeMessage']['status'];

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
 * `PAYMENT_PROCESSING` is the state the ESB reports together with `202` when the payment
 * outcome is unknown and a reconciliation job owns the workflow. The browser must wait and
 * poll; it must never resend the booking or payment command.
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
          'The payment result is being verified with the payment provider. Your seats stay held and this page reloads the authoritative status until the outcome is settled. Do not submit the booking again.',
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
        description: 'The booking did not complete. Any held seats were released.',
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
          'This status is not one the browser recognises. The booking service remains authoritative; reload for the current state.',
        inProgress: false,
      };
  }
}
