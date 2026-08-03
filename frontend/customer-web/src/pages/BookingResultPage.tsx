import { Link, useParams, useSearchParams } from "react-router-dom";
import { CheckCircle2, Clock3, Ticket } from "lucide-react";
import { Badge, Card, Spinner } from "@event-ticketing/shared-ui";
import { useBooking, useEsb } from "../app/hooks";
import {
  BookingStatusSocket,
  statusSocketUrl,
  type StatusEvent,
} from "../api/websocket-client";
import { useEffect, useState } from "react";
import { QueryState } from "./PageState";
export function BookingResultPage() {
  const { bookingId } = useParams();
  const [params] = useSearchParams();
  const esb = useEsb();
  const result = useBooking(bookingId);
  const [liveState, setLiveState] = useState<
    "connecting" | "open" | "closed" | "error"
  >("connecting");
  const [liveEvent, setLiveEvent] = useState<StatusEvent | null>(null);
  useEffect(() => {
    const currentBookingId = bookingId;
    const url = currentBookingId ? statusSocketUrl(currentBookingId) : "";
    if (!url || !currentBookingId) {
      setLiveState("closed");
      return undefined;
    }
    const socket = new BookingStatusSocket(url, {
      ticketProvider: () => esb.issueRealtimeWsTicket(currentBookingId),
    });
    return socket.connect(
      setLiveEvent,
      setLiveState,
      () => void result.refetch(),
    );
  }, [bookingId, esb]);
  if (result.isLoading)
    return (
      <section className="container page-section page-state">
        <Spinner label="Loading booking status" />
      </section>
    );
  if (result.isError || !result.data)
    return (
      <QueryState error={result.error} retry={() => void result.refetch()} />
    );
  const booking = result.data;
  const status = liveEvent?.status ?? booking.status;
  return (
    <section className="container page-section narrow-page">
      <Card className="result-card">
        <div className="result-icon">
          <CheckCircle2 size={34} />
        </div>
        <p className="eyebrow">
          {params.get("created") ? "Booking received" : "Booking status"}
        </p>
        <h1>
          {status === "CONFIRMED"
            ? "You are all set"
            : "Your booking is being processed"}
        </h1>
        <p className="lede">
          Booking <strong>{booking.bookingId}</strong> has status{" "}
          <Badge tone={status === "CONFIRMED" ? "success" : "warning"}>
            {status}
          </Badge>
          .
        </p>
        {liveState === "open" ? (
          <p className="live-note">
            <span className="live-dot" /> Live updates connected
            {liveEvent?.message ? ` — ${liveEvent.message}` : ""}
          </p>
        ) : (
          <p className="live-note">
            <Clock3 size={16} /> Live updates are unavailable; this page
            refreshes automatically.
          </p>
        )}
        <div className="result-actions">
          <Link
            to={`/bookings/${booking.bookingId}`}
            className="button button-primary"
          >
            <Ticket size={17} /> View booking
          </Link>
          <Link to="/events" className="button button-secondary">
            Browse more events
          </Link>
        </div>
      </Card>
    </section>
  );
}
