import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ExternalLink, Search, XCircle, RotateCcw } from 'lucide-react';
import { Badge, Button, Card, Input, Pagination } from '@event-ticketing/shared-ui';
import { useAdminBooking, useAdminBookings, useBookingAction } from '../hooks/useAdminApi';
import { PageHeader } from '../components/AppShell';
import { QueryState } from '../components/QueryState';
import { Table } from '../components/Table';
import type { BookingRecord } from '../types';

export function BookingManagementPage() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const query = useAdminBookings({ search, page, pageSize: 20 });
  return (
    <>
      <PageHeader
        eyebrow="Orders"
        title="Bookings"
        description="Review booking state and trigger compensating actions when the gateway allows it."
      />
      <Card>
        <div className="toolbar">
          <label className="search-control">
            <Search size={16} />
            <Input
              aria-label="Search bookings"
              placeholder="Booking or customer ID"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </label>
          <span className="toolbar-meta">
            {query.data ? `${query.data.total} bookings` : 'Live results'}
          </span>
        </div>
        <QueryState
          isLoading={query.isLoading}
          error={query.error}
          onRetry={() => void query.refetch()}
        >
          <Table<BookingRecord>
            rows={query.data?.items ?? []}
            columns={[
              {
                key: 'id',
                label: 'Booking',
                render: (row) => (
                  <div className="table-primary">
                    <Link to={`/bookings/${row.id}`} className="table-link">
                      {row.bookingId ?? row.id}
                    </Link>
                    <small>{row.customerId ?? 'Customer unavailable'}</small>
                  </div>
                ),
              },
              {
                key: 'event',
                label: 'Event',
                render: (row) => row.eventName ?? row.eventId ?? '—',
              },
              {
                key: 'status',
                label: 'Status',
                render: (row) => (
                  <Badge
                    tone={
                      row.status?.toLowerCase() === 'confirmed'
                        ? 'success'
                        : row.status?.toLowerCase() === 'cancelled'
                          ? 'danger'
                          : 'warning'
                    }
                  >
                    {row.status ?? 'Unknown'}
                  </Badge>
                ),
              },
              { key: 'payment', label: 'Payment', render: (row) => row.paymentStatus ?? '—' },
              {
                key: 'created',
                label: 'Created',
                render: (row) => (row.createdAt ? new Date(row.createdAt).toLocaleString() : '—'),
              },
              {
                key: 'open',
                label: '',
                render: (row) => (
                  <Link className="icon-link" to={`/bookings/${row.id}`} aria-label="Open booking">
                    <ExternalLink size={16} />
                  </Link>
                ),
              },
            ]}
          />
          {query.data && query.data.totalPages > 1 && (
            <Pagination page={page} pageCount={query.data.totalPages} onPageChange={setPage} />
          )}
        </QueryState>
      </Card>
    </>
  );
}

export function BookingDetailPage({ bookingId }: { bookingId: string }) {
  const navigate = useNavigate();
  const query = useAdminBooking(bookingId);
  const action = useBookingAction(bookingId);
  const booking = query.data;
  return (
    <>
      <PageHeader
        eyebrow="Booking"
        title={booking?.bookingId ?? bookingId}
        description="Authoritative booking state comes from the gateway."
        actions={
          <Button variant="secondary" onClick={() => navigate('/bookings')}>
            Back to bookings
          </Button>
        }
      />
      <QueryState
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => void query.refetch()}
      >
        {booking && (
          <div className="detail-grid">
            <Card>
              <dl className="detail-list">
                <div>
                  <dt>Event</dt>
                  <dd>{booking.eventName ?? booking.eventId ?? '—'}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <Badge
                      tone={booking.status?.toLowerCase() === 'confirmed' ? 'success' : 'warning'}
                    >
                      {booking.status ?? 'Unknown'}
                    </Badge>
                  </dd>
                </div>
                <div>
                  <dt>Payment</dt>
                  <dd>{booking.paymentStatus ?? '—'}</dd>
                </div>
                <div>
                  <dt>Customer</dt>
                  <dd>{booking.customerId ?? '—'}</dd>
                </div>
                <div>
                  <dt>Total</dt>
                  <dd>
                    {booking.total !== undefined
                      ? `${booking.total} ${booking.currency ?? ''}`
                      : '—'}
                  </dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{booking.createdAt ? new Date(booking.createdAt).toLocaleString() : '—'}</dd>
                </div>
              </dl>
            </Card>
            <Card>
              <h3>Actions</h3>
              <p className="muted">
                Every action is delegated to the booking orchestrator and may fail if its state
                transition is not allowed.
              </p>
              <div className="stack-actions">
                <Button
                  variant="secondary"
                  icon={<XCircle size={16} />}
                  loading={action.isPending && action.variables === 'cancel'}
                  onClick={() => action.mutate('cancel')}
                >
                  Cancel booking
                </Button>
                <Button
                  variant="secondary"
                  icon={<RotateCcw size={16} />}
                  loading={action.isPending && action.variables === 'refund'}
                  onClick={() => action.mutate('refund')}
                >
                  Request refund
                </Button>
              </div>
              {action.error && (
                <p className="form-error" role="alert">
                  {action.error instanceof Error ? action.error.message : 'Action failed.'}
                </p>
              )}
            </Card>
          </div>
        )}
      </QueryState>
    </>
  );
}
