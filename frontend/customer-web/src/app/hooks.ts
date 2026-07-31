import { useMemo } from 'react';
import { useMutation, useQuery, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';
import { EsbClient, type Booking, type EventSummary, type Page, type SeatMap, type Ticket } from '../api/esb-client';
import { useAuth } from './auth';

export function useEsb(): EsbClient { const { client } = useAuth(); return useMemo(() => new EsbClient({ getToken: () => client.token }), [client]); }
export function useEvents(params: { query?: string; category?: string; from?: string; to?: string; page?: number } = {}): UseQueryResult<Page<EventSummary>> { const esb = useEsb(); return useQuery({ queryKey: ['events', params], queryFn: () => esb.listEvents(params), staleTime: 30_000 }); }
export function useEvent(eventId: string | undefined): UseQueryResult<EventSummary> { const esb = useEsb(); return useQuery({ queryKey: ['event', eventId], queryFn: () => esb.getEvent(eventId as string), enabled: Boolean(eventId), staleTime: 30_000 }); }
export function useSeatMap(eventId: string | undefined): UseQueryResult<SeatMap> { const esb = useEsb(); return useQuery({ queryKey: ['seat-map', eventId], queryFn: () => esb.getSeatMap(eventId as string), enabled: Boolean(eventId), staleTime: 5_000 }); }
export function useBookings(enabled: boolean): UseQueryResult<Page<Booking>> { const esb = useEsb(); return useQuery({ queryKey: ['bookings'], queryFn: () => esb.listBookings(), enabled, staleTime: 10_000 }); }
export function useBooking(bookingId: string | undefined, enabled = true): UseQueryResult<Booking> { const esb = useEsb(); return useQuery({ queryKey: ['booking', bookingId], queryFn: () => esb.getBooking(bookingId as string), enabled: Boolean(bookingId) && enabled, refetchInterval: 15_000 }); }
export function useTicket(ticketId: string | undefined, enabled = true): UseQueryResult<Ticket> { const esb = useEsb(); return useQuery({ queryKey: ['ticket', ticketId], queryFn: () => esb.getTicket(ticketId as string), enabled: Boolean(ticketId) && enabled }); }
export function useReserveSeats(): UseMutationResult<import('../api/esb-client').Reservation, unknown, { eventId: string; seatIds: string[]; idempotencyKey: string }> { const esb = useEsb(); return useMutation({ mutationFn: (payload) => esb.reserveSeats(payload) }); }
export function useCreateBooking(): UseMutationResult<Booking, unknown, { eventId: string; reservationId: string; paymentMethod: string; idempotencyKey: string }> { const esb = useEsb(); return useMutation({ mutationFn: (payload) => esb.createBooking(payload) }); }
