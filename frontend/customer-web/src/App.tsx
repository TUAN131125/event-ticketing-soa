import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { createQueryClient } from './app/query-client';
import { AuthProvider } from './app/auth';
import { RequireAuth } from './app/RequireAuth';
import { Shell } from './app/Shell';
import { EventListPage } from './pages/EventListPage';
import { EventDetailPage } from './pages/EventDetailPage';
import { SeatSelectionPage } from './pages/SeatSelectionPage';
import { CheckoutPage } from './pages/CheckoutPage';
import { BookingResultPage } from './pages/BookingResultPage';
import { MyBookingsPage } from './pages/MyBookingsPage';
import { BookingDetailPage } from './pages/BookingDetailPage';
import { TicketDetailPage } from './pages/TicketDetailPage';
import { TicketWalletPage } from './pages/TicketWalletPage';
import { ContactDetailsPage } from './pages/ContactDetailsPage';
import { LoginPage, RegisterPage, AccountPage } from './pages/AuthPages';
import { NotFoundState } from '@event-ticketing/shared-ui';
import { Component, type ErrorInfo, type ReactNode } from 'react';

const queryClient = createQueryClient();
class GlobalErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* the host logger can capture this boundary */
  }
  render() {
    return this.state.hasError ? (
      <NotFoundState
        title="We hit an unexpected error"
        description="Refresh the page to continue. No booking was changed."
        action={
          <button className="button button-primary" onClick={() => window.location.reload()}>
            Refresh
          </button>
        }
      />
    ) : (
      this.props.children
    );
  }
}
export default function App() {
  return (
    <GlobalErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route element={<Shell />}>
                <Route index element={<Navigate to="/events" replace />} />
                <Route path="events" element={<EventListPage />} />
                <Route path="events/:eventId" element={<EventDetailPage />} />
                <Route path="login" element={<LoginPage />} />
                <Route path="register" element={<RegisterPage />} />
                <Route
                  path="account"
                  element={
                    <RequireAuth>
                      <AccountPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="events/:eventId/seats"
                  element={
                    <RequireAuth>
                      <SeatSelectionPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="checkout/contact"
                  element={
                    <RequireAuth>
                      <ContactDetailsPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="checkout"
                  element={
                    <RequireAuth>
                      <CheckoutPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="bookings"
                  element={
                    <RequireAuth>
                      <MyBookingsPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="bookings/:bookingId"
                  element={
                    <RequireAuth>
                      <BookingDetailPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="bookings/:bookingId/status"
                  element={
                    <RequireAuth>
                      <BookingResultPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="tickets"
                  element={
                    <RequireAuth>
                      <TicketWalletPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="tickets/:ticketId"
                  element={
                    <RequireAuth>
                      <TicketDetailPage />
                    </RequireAuth>
                  }
                />
                <Route
                  path="*"
                  element={
                    <NotFoundState
                      title="Page not found"
                      description="That page does not exist."
                      action={
                        <a className="button button-primary" href="/events">
                          Browse events
                        </a>
                      }
                    />
                  }
                />
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </GlobalErrorBoundary>
  );
}
