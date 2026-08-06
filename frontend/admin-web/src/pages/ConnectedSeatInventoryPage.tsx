import { Navigate, useParams } from 'react-router-dom';
import { useAdminSession } from '../app/useAdminSession';
import { SeatInventoryPage } from './SeatInventoryPage';

export function ConnectedSeatInventoryPage() {
  const { accessToken } = useAdminSession();
  const { eventId } = useParams();
  if (!eventId) return <Navigate to="/events" replace />;
  return <SeatInventoryPage accessToken={accessToken} eventId={eventId} />;
}
