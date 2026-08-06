import { useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CalendarDays, MapPin, Search, SlidersHorizontal } from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Select,
  Skeleton,
  Pagination,
} from '@event-ticketing/shared-ui';
import { useEvents } from '../app/hooks';
import { QueryState } from './PageState';

function formatDate(value?: string) {
  if (!value) return 'Date to be announced';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date);
}
export function EventListPage() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get('q') ?? '');
  const result = useEvents({
    query: params.get('q') ?? undefined,
    status: params.get('status') ?? undefined,
    page: Number(params.get('page') ?? 1),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams(params);
    if (query) next.set('q', query);
    else next.delete('q');
    next.set('page', '1');
    setParams(next);
  };
  return (
    <section className="container page-section">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Find your next night out</p>
          <h1>Events worth showing up for</h1>
          <p className="lede">
            Explore live music, theatre, sport and ideas from trusted organisers.
          </p>
        </div>
      </div>
      <form className="search-bar" onSubmit={submit}>
        <label className="sr-only" htmlFor="event-search">
          Search events
        </label>
        <Search size={19} aria-hidden="true" />
        <Input
          id="event-search"
          value={query}
          onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
          placeholder="Search by event, city or venue"
        />
        <Select
          aria-label="Filter by sale status"
          value={params.get('status') ?? ''}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => {
            const next = new URLSearchParams(params);
            if (event.target.value) {
              next.set('status', event.target.value);
            } else {
              next.delete('status');
            }
            next.set('page', '1');
            setParams(next);
          }}
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="ON_SALE">On sale</option>
          <option value="PAUSED">Paused</option>
          <option value="ENDED">Ended</option>
          <option value="CANCELLED">Cancelled</option>
        </Select>
        <Button type="submit">
          <SlidersHorizontal size={17} /> Search
        </Button>
      </form>
      {result.isPending && !result.isError ? (
        <div className="event-grid">
          {[1, 2, 3].map((item) => (
            <Card key={item} padded>
              <Skeleton height={180} />
              <Skeleton width="60%" />
              <Skeleton width="45%" />
            </Card>
          ))}
        </div>
      ) : result.isError ? (
        <QueryState
          error={result.error}
          retry={() => void result.refetch()}
          serviceName="event service"
        />
      ) : result.data?.items.length ? (
        <>
          <div className="section-toolbar">
            <span>{result.data.total} events</span>
          </div>
          <div className="event-grid">
            {result.data.items.map((item) => (
              <Card key={item.eventId} className="event-card">
                <div className="event-cover">
                  <CalendarDays size={32} />
                </div>
                <div className="event-card-body">
                  <div className="event-card-meta">
                    <Badge tone="information">{item.status || 'Status unavailable'}</Badge>
                  </div>
                  <h2>
                    <Link to={`/events/${encodeURIComponent(item.eventId)}`}>{item.name}</Link>
                  </h2>
                  <p>
                    <CalendarDays size={15} /> {formatDate(item.startsAt)}
                  </p>
                  <p>
                    <MapPin size={15} /> {item.venue || 'Venue details to be announced'}
                  </p>
                </div>
              </Card>
            ))}
          </div>
          <Pagination
            page={result.data.page}
            pageCount={Math.max(1, Math.ceil(result.data.total / result.data.pageSize))}
            onPageChange={(page: number) => {
              const next = new URLSearchParams(params);
              next.set('page', String(page));
              setParams(next);
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
          />
        </>
      ) : (
        <EmptyState
          title="No events found"
          description="Try a broader search or check back soon for new listings."
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setQuery('');
                setParams({});
              }}
            >
              Clear filters
            </Button>
          }
        />
      )}
    </section>
  );
}
