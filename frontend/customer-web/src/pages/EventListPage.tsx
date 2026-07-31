import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CalendarDays, MapPin, Search, SlidersHorizontal } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Select,
  Skeleton,
} from "@event-ticketing/shared-ui";
import { useEvents } from "../app/hooks";
import { QueryState } from "./PageState";

function formatDate(value?: string) {
  if (!value) return "Date to be announced";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}
export function EventListPage() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const result = useEvents({
    query: params.get("q") ?? undefined,
    category: params.get("category") ?? undefined,
    page: Number(params.get("page") ?? 1),
  });
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams(params);
    if (query) next.set("q", query);
    else next.delete("q");
    setParams(next);
  };
  return (
    <section className="container page-section">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Find your next night out</p>
          <h1>Events worth showing up for</h1>
          <p className="lede">
            Explore live music, theatre, sport and ideas from trusted
            organisers.
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
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by event, city or venue"
        />
        <Select
          aria-label="Filter by category"
          value={params.get("category") ?? ""}
          onChange={(event) => {
            const next = new URLSearchParams(params);
            if (event.target.value) {
              next.set("category", event.target.value);
            } else {
              next.delete("category");
            }
            setParams(next);
          }}
        >
          <option value="">All categories</option>
          <option value="MUSIC">Music</option>
          <option value="THEATRE">Theatre</option>
          <option value="SPORT">Sport</option>
          <option value="CONFERENCE">Conference</option>
        </Select>
        <Button type="submit">
          <SlidersHorizontal size={17} /> Search
        </Button>
      </form>
      {result.isLoading ? (
        <div className="event-grid">
          {[1, 2, 3].map((item) => (
            <Card key={item}>
              <Skeleton height={180} />
              <Skeleton width="60%" />
              <Skeleton width="45%" />
            </Card>
          ))}
        </div>
      ) : result.isError ? (
        <QueryState error={result.error} retry={() => void result.refetch()} />
      ) : result.data?.items.length ? (
        <>
          <div className="section-toolbar">
            <span>{result.data.total} events</span>
          </div>
          <div className="event-grid">
            {result.data.items.map((item) => (
              <Card key={item.eventId} className="event-card">
                <div className="event-cover">
                  {item.imageUrl ? (
                    <img src={item.imageUrl} alt="" />
                  ) : (
                    <CalendarDays size={32} />
                  )}
                </div>
                <div className="event-card-body">
                  <div className="event-card-meta">
                    <Badge tone="information">
                      {item.category || "Live event"}
                    </Badge>
                    {item.status && <span>{item.status}</span>}
                  </div>
                  <h2>
                    <Link to={`/events/${encodeURIComponent(item.eventId)}`}>
                      {item.name}
                    </Link>
                  </h2>
                  <p>
                    <CalendarDays size={15} /> {formatDate(item.startsAt)}
                  </p>
                  <p>
                    <MapPin size={15} />{" "}
                    {item.venue || "Venue details to be announced"}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        </>
      ) : (
        <EmptyState
          title="No events found"
          description="Try a broader search or check back soon for new listings."
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setQuery("");
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
