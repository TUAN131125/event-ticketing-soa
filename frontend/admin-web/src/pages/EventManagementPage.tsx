import { useEffect, useState } from 'react';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate } from 'react-router-dom';
import { CalendarPlus, ExternalLink, Plus, Search, Send } from 'lucide-react';
import { Badge, Button, Card, Input, Pagination } from '@event-ticketing/shared-ui';
import { useAdminEvent, useAdminEvents, usePublishEvent, useSaveEvent } from '../hooks/useAdminApi';
import { PageHeader } from '../components/AppShell';
import { QueryState } from '../components/QueryState';
import { Table } from '../components/Table';
import type { EventRecord } from '../types';

const eventSchema = z.object({ name: z.string().trim().min(2, 'Enter an event name'), venue: z.string().trim().min(2, 'Enter a venue'), startsAt: z.string().min(1, 'Choose a start time'), description: z.string().optional() });
type EventFormValues = z.infer<typeof eventSchema>;

export function EventManagementPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const query = useAdminEvents({ search, page, pageSize: 20 });
  const publish = usePublishEvent();
  const rows = query.data?.items ?? [];
  return <>
    <PageHeader eyebrow="Catalogue" title="Events" description="Create, review and publish events exposed through the booking gateway." actions={<Button icon={<Plus size={17} />} onClick={() => navigate('/events/new')}>New event</Button>} />
    <Card><div className="toolbar"><label className="search-control"><Search size={16} /><Input aria-label="Search events" placeholder="Search by name or venue" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label><span className="toolbar-meta">{query.data ? `${query.data.total} events` : 'Live results'}</span></div>
      <QueryState isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        <Table<EventRecord> rows={rows} columns={[
          { key: 'event', label: 'Event', render: (row) => <div className="table-primary"><strong>{row.name}</strong><small>{row.venue || 'Venue pending'}</small></div> },
          { key: 'date', label: 'Starts', render: (row) => row.startsAt ? new Date(row.startsAt).toLocaleString() : '—' },
          { key: 'status', label: 'Status', render: (row) => <Badge tone={row.status?.toLowerCase() === 'published' ? 'success' : 'neutral'}>{row.status || 'Unknown'}</Badge> },
          { key: 'inventory', label: 'Inventory', render: (row) => <span>{row.bookedCount ?? 0}{row.capacity ? ` / ${row.capacity}` : ''}</span> },
          { key: 'actions', label: '', render: (row) => <div className="table-actions"><Link className="icon-link" to={`/events/${row.id}`} aria-label={`Open ${row.name}`}><ExternalLink size={16} /></Link>{row.status?.toLowerCase() !== 'published' && <Button variant="ghost" size="sm" icon={<Send size={15} />} loading={publish.isPending && publish.variables === row.id} onClick={() => publish.mutate(row.id)}>Publish</Button>}</div> },
        ]} />
        {query.data && query.data.totalPages > 1 && <Pagination page={page} pageCount={query.data.totalPages} onPageChange={setPage} />}
      </QueryState>
    </Card>
  </>;
}

export function EventEditorPage({ eventId }: { eventId?: string }) {
  const navigate = useNavigate();
  const form = useForm<EventFormValues>({ resolver: zodResolver(eventSchema), defaultValues: { name: '', venue: '', startsAt: '', description: '' } });
  const detail = useAdminEvent(eventId);
  useEffect(() => { if (detail.data) form.reset({ name: detail.data.name, venue: detail.data.venue ?? '', startsAt: detail.data.startsAt?.slice(0, 16) ?? '', description: '' }); }, [detail.data, form]);
  const mutation = useSaveEvent(eventId);
  return <><PageHeader eyebrow={eventId ? 'Edit event' : 'New event'} title={eventId ? 'Update event details' : 'Create an event'} description="Changes are sent to the gateway; no local draft is persisted." /><Card><QueryState isLoading={Boolean(eventId && detail.isLoading)} error={eventId ? detail.error : undefined} onRetry={() => void detail.refetch()}><form className="form-grid" onSubmit={form.handleSubmit((values) => mutation.mutate(values))} noValidate><label>Event name<Input required {...form.register('name')} /></label>{form.formState.errors.name && <span className="form-error">{form.formState.errors.name.message}</span>}<label>Venue<Input required {...form.register('venue')} /></label>{form.formState.errors.venue && <span className="form-error">{form.formState.errors.venue.message}</span>}<label>Starts at<Input required type="datetime-local" {...form.register('startsAt')} /></label>{form.formState.errors.startsAt && <span className="form-error">{form.formState.errors.startsAt.message}</span>}<label className="form-span-2">Description<textarea {...form.register('description')} rows={5} /></label>{mutation.error && <p className="form-error" role="alert">{mutation.error instanceof Error ? mutation.error.message : 'Could not save event.'}</p>}<div className="form-actions"><Button type="button" variant="secondary" onClick={() => navigate('/events')}>Cancel</Button><Button type="submit" loading={mutation.isPending} icon={<CalendarPlus size={16} />}>Save event</Button></div></form></QueryState></Card></>;
}
