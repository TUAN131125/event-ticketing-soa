import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AdminShell } from './app/AdminShell';
import { AuthProvider } from './auth/AuthProvider';
import { ConnectedCheckInPage } from './pages/ConnectedCheckInPage';
import { ConnectedEventFormPage } from './pages/ConnectedEventFormPage';
import { ConnectedEventsPage } from './pages/ConnectedEventsPage';
import { ConnectedOverviewPage } from './pages/ConnectedOverviewPage';
import { ConnectedSeatInventoryPage } from './pages/ConnectedSeatInventoryPage';
import { ConnectedWorkflowTracesPage } from './pages/ConnectedWorkflowTracesPage';
import { LoginPage } from './pages/LoginPage';
import './styles/admin.css';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<AdminShell />}>
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<ConnectedOverviewPage />} />
            <Route path="/events" element={<ConnectedEventsPage />} />
            <Route path="/events/new" element={<ConnectedEventFormPage />} />
            <Route path="/events/:eventId/edit" element={<ConnectedEventFormPage />} />
            <Route path="/events/:eventId/seats" element={<ConnectedSeatInventoryPage />} />
            <Route path="/check-in" element={<ConnectedCheckInPage />} />
            <Route path="/traces" element={<ConnectedWorkflowTracesPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
