import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { esbAdminClient } from '../api/esb';
import { useAuth } from '../auth/AuthProvider';
import type { EventInput, ListParams, NotificationRecord, Page, PaymentRecord, TraceRecord, User } from '../types';
type ResourceRecord = PaymentRecord | NotificationRecord | TraceRecord;

export function useAdminOverview() {
  const { session } = useAuth();
  return useQuery({ queryKey: ['admin-overview'], queryFn: () => esbAdminClient.overview(session!.accessToken), enabled: Boolean(session), retry: false, staleTime: 30_000 });
}
export function useAdminEvents(params: ListParams) { const { session } = useAuth(); return useQuery({ queryKey: ['admin-events', params], queryFn: () => esbAdminClient.events(session!.accessToken, params), enabled: Boolean(session), retry: false }); }
export function useAdminEvent(id?: string) { const { session } = useAuth(); return useQuery({ queryKey: ['admin-event', id], queryFn: () => esbAdminClient.event(session!.accessToken, id!), enabled: Boolean(session && id), retry: false }); }
export function usePublishEvent() { const { session } = useAuth(); const client = useQueryClient(); return useMutation({ mutationFn: (id: string) => esbAdminClient.publishEvent(session!.accessToken, id), onSuccess: () => void client.invalidateQueries({ queryKey: ['admin-events'] }) }); }
export function useSaveEvent(eventId?: string) { const { session } = useAuth(); const client = useQueryClient(); return useMutation({ mutationFn: (input: EventInput) => eventId ? esbAdminClient.updateEvent(session!.accessToken, eventId, input) : esbAdminClient.createEvent(session!.accessToken, input), onSuccess: () => void client.invalidateQueries({ queryKey: ['admin-events'] }) }); }
export function useAdminBookings(params: ListParams) { const { session } = useAuth(); return useQuery({ queryKey: ['admin-bookings', params], queryFn: () => esbAdminClient.bookings(session!.accessToken, params), enabled: Boolean(session), retry: false }); }
export function useAdminBooking(id: string) { const { session } = useAuth(); return useQuery({ queryKey: ['admin-booking', id], queryFn: () => esbAdminClient.booking(session!.accessToken, id), enabled: Boolean(session && id), retry: false }); }
export function useBookingAction(id: string) { const { session } = useAuth(); const client = useQueryClient(); return useMutation({ mutationFn: (kind: 'cancel' | 'refund') => kind === 'cancel' ? esbAdminClient.cancelBooking(session!.accessToken, id) : esbAdminClient.refundBooking(session!.accessToken, id), onSuccess: () => void client.invalidateQueries({ queryKey: ['admin-booking', id] }) }); }
export function useAdminResource(kind: 'payments' | 'notifications' | 'monitoring', params: ListParams) { const { session } = useAuth(); return useQuery<Page<ResourceRecord>>({ queryKey: [kind, params], queryFn: async () => { if (kind === 'payments') return esbAdminClient.payments(session!.accessToken, params) as Promise<Page<ResourceRecord>>; if (kind === 'notifications') return esbAdminClient.notifications(session!.accessToken, params) as Promise<Page<ResourceRecord>>; return esbAdminClient.traces(session!.accessToken, params) as Promise<Page<ResourceRecord>>; }, enabled: Boolean(session), retry: false }); }
export function useAdminUsers(params: ListParams) { const { session } = useAuth(); return useQuery({ queryKey: ['admin-users', params], queryFn: () => esbAdminClient.users(session!.accessToken, params), enabled: Boolean(session), retry: false }); }
export function useAssignRole() { const { assignRole } = useAuth(); return useMutation({ mutationFn: ({ userId, role, action }: { userId: string; role: User['roles'][number]; action: 'assign' | 'revoke' }) => assignRole(userId, role, action) }); }
