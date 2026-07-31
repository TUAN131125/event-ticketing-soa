export type Role = 'CUSTOMER' | 'ADMIN' | 'CHECKIN_STAFF' | 'SERVICE' | string;

export type User = {
  id: string;
  email: string;
  displayName?: string;
  roles: Role[];
  status?: 'ACTIVE' | 'DISABLED' | 'LOCKED' | string;
};

export type AuthSession = {
  accessToken: string;
  user: User;
  expiresAt?: string;
};

export type EventRecord = {
  id: string;
  name: string;
  slug?: string;
  venue?: string;
  startsAt?: string;
  endsAt?: string;
  status?: string;
  inventoryStatus?: string;
  capacity?: number;
  bookedCount?: number;
  imageUrl?: string;
};

export type BookingRecord = {
  id: string;
  bookingId?: string;
  customerId?: string;
  eventId?: string;
  eventName?: string;
  status?: string;
  paymentStatus?: string;
  total?: number;
  currency?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type PaymentRecord = {
  id: string;
  bookingId?: string;
  amount?: number;
  currency?: string;
  status?: string;
  provider?: string;
  createdAt?: string;
};

export type NotificationRecord = {
  id: string;
  channel?: string;
  recipient?: string;
  status?: string;
  template?: string;
  createdAt?: string;
};

export type TraceRecord = {
  traceId: string;
  correlationId?: string;
  operation?: string;
  status?: string;
  durationMs?: number;
  startedAt?: string;
};

export type Page<T> = {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
};

export type AdminOverview = {
  events?: number;
  bookings?: number;
  activeBookings?: number;
  revenue?: number;
  currency?: string;
  serviceHealth?: Array<{ name: string; status: string; latencyMs?: number }>;
};

export type EventInput = {
  name: string;
  venue: string;
  startsAt: string;
  endsAt?: string;
  description?: string;
  capacity?: number;
};

export type ListParams = { page?: number; pageSize?: number; search?: string; status?: string };
