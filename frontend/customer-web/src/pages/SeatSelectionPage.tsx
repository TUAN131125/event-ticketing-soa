import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Armchair, ArrowRight, Info } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Spinner,
} from "@event-ticketing/shared-ui";
import { useAuth } from "../app/auth";
import { useEvent, useReserveSeats, useSeatMap } from "../app/hooks";
import { ApiError } from "../api/auth-client";
import { QueryState } from "./PageState";

export function SeatSelectionPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const event = useEvent(eventId);
  const map = useSeatMap(eventId);
  const [selected, setSelected] = useState<string[]>([]);
  const reserve = useReserveSeats();
  if (!user) return null;
  if (event.isLoading || map.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading live seat inventory" />
      </section>
    );
  if (event.isError)
    return (
      <QueryState error={event.error} retry={() => void event.refetch()} />
    );
  if (map.isError)
    return <QueryState error={map.error} retry={() => void map.refetch()} />;
  const seats = map.data?.seats ?? [];
  if (!seats.length)
    return (
      <EmptyState
        title="Seat inventory is not available"
        description="The organiser has not published seat inventory for this event yet."
        action={
          <Link to={`/events/${eventId}`} className="button button-secondary">
            Back to event
          </Link>
        }
      />
    );
  const total = selected.reduce(
    (sum, id) => sum + (seats.find((seat) => seat.seatId === id)?.price ?? 0),
    0,
  );
  return (
    <section className="container page-section">
      <Link to={`/events/${eventId}`} className="back-link">
        ← {event.data?.name}
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Step 1 of 2</p>
          <h1>Choose your seats</h1>
          <p className="lede">
            Select available seats. Inventory is held only after you continue.
          </p>
        </div>
      </div>
      <div className="seat-layout">
        <Card className="seat-map-card">
          <div className="seat-stage">STAGE</div>
          <div className="seat-grid" role="group" aria-label="Seat map">
            {seats.map((seat) => {
              const unavailable = seat.status !== "AVAILABLE";
              const active = selected.includes(seat.seatId);
              return (
                <button
                  key={seat.seatId}
                  type="button"
                  className={`seat ${active ? "seat-selected" : ""} ${unavailable ? "seat-unavailable" : ""}`}
                  disabled={unavailable || reserve.isPending}
                  aria-pressed={active}
                  aria-label={`${seat.label || seat.seatId}, ${unavailable ? seat.status.toLowerCase() : "available"}`}
                  onClick={() =>
                    setSelected((current) =>
                      active
                        ? current.filter((item) => item !== seat.seatId)
                        : [...current, seat.seatId],
                    )
                  }
                >
                  <Armchair size={15} />
                  <span>{seat.label || seat.seatId}</span>
                </button>
              );
            })}
          </div>
          <div className="seat-legend">
            <span>
              <i className="legend-dot available" /> Available
            </span>
            <span>
              <i className="legend-dot selected" /> Selected
            </span>
            <span>
              <i className="legend-dot unavailable" /> Unavailable
            </span>
          </div>
        </Card>
        <Card className="booking-panel">
          <Badge tone="information">{event.data?.name}</Badge>
          <h2>Your selection</h2>
          {selected.length ? (
            <ul className="selection-list">
              {selected.map((id) => {
                const seat = seats.find((item) => item.seatId === id);
                return (
                  <li key={id}>
                    <span>{seat?.label || id}</span>
                    <strong>
                      {seat?.price
                        ? `${seat.currency ?? "VND"} ${seat.price.toLocaleString()}`
                        : "Price on checkout"}
                    </strong>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="muted">
              <Info size={16} /> Choose at least one available seat.
            </p>
          )}
          <div className="total-row">
            <span>Estimated total</span>
            <strong>{total ? `VND ${total.toLocaleString()}` : "—"}</strong>
          </div>
          <Button
            fullWidth
            disabled={!selected.length || reserve.isPending}
            onClick={() =>
              reserve.mutate(
                {
                  eventId: eventId as string,
                  seatIds: selected,
                  idempotencyKey: crypto.randomUUID(),
                },
                {
                  onSuccess: (result) =>
                    navigate(
                      `/checkout?reservationId=${encodeURIComponent(result.reservationId)}&eventId=${encodeURIComponent(eventId as string)}`,
                    ),
                },
              )
            }
          >
            {reserve.isPending ? "Holding seats…" : "Continue to checkout"}{" "}
            <ArrowRight size={17} />
          </Button>
          {reserve.isError && (
            <p className="form-error">
              {reserve.error instanceof ApiError
                ? reserve.error.message
                : "Seats could not be held. Refresh and try again."}
            </p>
          )}
        </Card>
      </div>
    </section>
  );
}
