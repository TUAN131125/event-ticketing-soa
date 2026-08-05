import { useMemo } from 'react';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';
import { useAuth } from './auth';
import {
  DEFAULT_BOOKING_POLL_SECONDS,
  EsbClient,
  type Booking,
  type BookingSubmission,
  type PlaceBookingRequest,
} from '../api/esb-client';
import { isSettled } from '../domain/booking-status';

export function useEsb(): EsbClient {
  const { client } = useAuth();
  return useMemo(() => new EsbClient({ getToken: () => client.token }), [client]);
}

export function useEvents(params: { query?: string; category?: string; page?: number } = {}) {
  const esb = useEsb();
  return useQuery({
    queryKey: ['events', params],
    queryFn: () => esb.listEvents(params),
  });
}

export function useEvent(eventId?: string) {
  const esb = useEsb();
  return useQuery({
    queryKey: ['event', eventId],
    queryFn: () => esb.getEvent(eventId as string),
    enabled: Boolean(eventId),
  });
}

/**
 * Reads the authoritative booking state. While the workflow is unsettled the query polls
 * `GET /api/bookings/{bookingId}`; when the ESB answered `202` it honours the server's
 * `Retry-After` instead of a hard-coded interval. The booking command is never resent.
 */
export function useBooking(bookingId?: string, retryAfterSeconds?: number | null) {
  const esb = useEsb();
  const intervalMs = Math.max(1, retryAfterSeconds ?? DEFAULT_BOOKING_POLL_SECONDS) * 1000;
  return useQuery({
    queryKey: ['booking', bookingId],
    queryFn: () => esb.getBooking(bookingId as string),
    enabled: Boolean(bookingId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isSettled(status) ? false : intervalMs;
    },
  });
}

export function useCreateBooking(): UseMutationResult<
  BookingSubmission,
  unknown,
  { payload: PlaceBookingRequest; idempotencyKey: string }
> {
  const esb = useEsb();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ payload, idempotencyKey }) => esb.createBooking(payload, idempotencyKey),
    onSuccess: (submission) =>
      queryClient.setQueryData(['booking', submission.booking.bookingId], submission.booking),
  });
}

export function useCancelBooking(bookingId: string) {
  const esb = useEsb();
  const queryClient = useQueryClient();
  return useMutation<Booking, unknown, void>({
    mutationFn: () => esb.cancelBooking(bookingId),
    onSuccess: (booking) => queryClient.setQueryData(['booking', bookingId], booking),
  });
}
