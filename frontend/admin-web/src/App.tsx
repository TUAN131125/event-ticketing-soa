import { Component, type ErrorInfo, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@event-ticketing/shared-ui';
import { AuthProvider } from './auth/AuthProvider';
import { AppShell } from './components/AppShell';
import { ProtectedRoute, LoginOnlyRoute } from './routes/guards';
import { AdminLoginPage } from './pages/AuthPages';
import { DashboardPage } from './pages/DashboardPage';
import { EventManagementPage, EventEditorPage } from './pages/EventManagementPage';
import { BookingManagementPage, BookingDetailPage } from './pages/BookingManagementPage';
import { ResourceListPage } from './pages/ResourceListPage';
import { UserManagementPage } from './pages/UserManagementPage';
import { NotFoundPage } from './pages/NotFoundPage';
import './styles/admin.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } },
});

class GlobalErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Admin UI error', error, info);
  }
  render() {
    if (this.state.error)
      return (
        <div className="centered-state">
          <h1>Something went wrong</h1>
          <p className="muted">Reload this page to restart the operations console.</p>
          <button className="native-button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      );
    return this.props.children;
  }
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <GlobalErrorBoundary>
              <Routes>
                <Route element={<LoginOnlyRoute />}>
                  <Route path="/login" element={<AdminLoginPage />} />
                </Route>
                <Route element={<ProtectedRoute roles={['ADMIN', 'OPERATOR']} />}>
                  <Route element={<AppShell />}>
                    <Route index element={<DashboardPage />} />
                    <Route path="events" element={<EventManagementPage />} />
                    <Route path="events/new" element={<EventEditorPage />} />
                    <Route path="events/:eventId" element={<EventEditorRoute />} />
                    <Route path="bookings" element={<BookingManagementPage />} />
                    <Route path="bookings/:bookingId" element={<BookingDetailRoute />} />
                    <Route path="payments" element={<ResourceListPage kind="payments" />} />
                    <Route
                      path="notifications"
                      element={<ResourceListPage kind="notifications" />}
                    />
                    <Route path="users" element={<UserManagementPage />} />
                    <Route path="monitoring" element={<ResourceListPage kind="monitoring" />} />
                    <Route path="health" element={<ResourceListPage kind="monitoring" />} />
                  </Route>
                </Route>
                <Route path="/404" element={<NotFoundPage />} />
                <Route path="*" element={<Navigate to="/404" replace />} />
              </Routes>
            </GlobalErrorBoundary>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

function EventEditorRoute() {
  const { eventId } = useParams();
  return <EventEditorPage eventId={eventId} />;
}
function BookingDetailRoute() {
  const { bookingId = '' } = useParams();
  return <BookingDetailPage bookingId={bookingId} />;
}
