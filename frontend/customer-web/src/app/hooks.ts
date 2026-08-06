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
  recentBookingIds,
  type Booking,
  type BookingSubmission,
  type PlaceBookingRequest,
} from '../api/esb-client';
import { ApiError } from '../api/auth-client';
import { isSettled } from '../domain/booking-status';

export function useEsb(): EsbClient {
  const { client } = useAuth();
  return useMemo(() => new EsbClient({ getToken: () => client.token }), [client]);
}

export function useEvents(params: { query?: string; status?: string; page?: number } = {}) {
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

export function useSeatMap(eventId?: string) {
  const esb = useEsb();
  return useQuery({
    queryKey: ['seat-map', eventId],
    queryFn: () => esb.getSeatMap(eventId as string),
    enabled: Boolean(eventId),
    refetchInterval: 20_000,
  });
}

/**
 * Polls authoritative booking state with a bounded schedule. The first two minutes use the
 * server-provided cadence, then polling slows to 30 seconds and stops after ten minutes. The
 * page remains usable and exposes manual refresh after the automatic budget is exhausted.
 */
export function useBooking(bookingId?: string, retryAfterSeconds?: number | null) {
  const esb = useEsb();
  const intervalMs = Math.max(1, retryAfterSeconds ?? DEFAULT_BOOKING_POLL_SECONDS) * 1000;
  const startedAt = useMemo(() => Date.now(), [bookingId]);
  return useQuery({
    queryKey: ['booking', bookingId],
    queryFn: () => esb.getBooking(bookingId as string),
    enabled: Boolean(bookingId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && isSettled(status)) return false;
      const elapsed = Date.now() - startedAt;
      if (elapsed > 10 * 60_000) return false;
      return elapsed > 2 * 60_000 ? 30_000 : intervalMs;
    },
  });
}

async function readRecentBookings(esb: EsbClient): Promise<Booking[]> {
  const ids = recentBookingIds();
  const results = await Promise.allSettled(ids.map((id) => esb.getBooking(id)));
  return results.flatMap((result) => (result.status === 'fulfilled' ? [result.value] : []));
}

/**
 * Uses the future owner-scoped list facade when available. Until the ESB expansion lands, a
 * 404/405/501 falls back to authoritative reads of recently used booking IDs. No local booking
 * status is trusted.
 */
export function useBookings(page = 1) {
  const esb = useEsb();
  return useQuery({
    queryKey: ['bookings', page],
    queryFn: async () => {
      try {
        const result = await esb.listBookings(page, 20);
        return { items: result.items, total: result.totalItems, source: 'owner-list' as const };
      } catch (error) {
        if (error instanceof ApiError && [404, 405, 501].includes(error.status)) {
          const items = await readRecentBookings(esb);
          return { items, total: items.length, source: 'recent-index' as const };
        }
        throw error;
      }
    },
    staleTime: 15_000,
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
    onSuccess: (submission) => {
      queryClient.setQueryData(['booking', submission.booking.bookingId], submission.booking);
      void queryClient.invalidateQueries({ queryKey: ['bookings'] });
    },
  });
}

export function useCancelBooking(bookingId: string) {
  const esb = useEsb();
  const queryClient = useQueryClient();
  return useMutation<Booking, unknown, { reason: string }>({
    mutationFn: ({ reason }) => esb.cancelBooking(bookingId, reason),
    onSuccess: (booking) => {
      queryClient.setQueryData(['booking', bookingId], booking);
      void queryClient.invalidateQueries({ queryKey: ['bookings'] });
    },
  });
}

export function useTickets(page = 1) {
  const esb = useEsb();
  return useQuery({
    queryKey: ['tickets', page],
    queryFn: () => esb.listTickets(page, 20),
  });
}

export function useTicket(ticketId?: string) {
  const esb = useEsb();
  return useQuery({
    queryKey: ['ticket', ticketId],
    queryFn: () => esb.getTicket(ticketId as string),
    enabled: Boolean(ticketId),
  });
}
