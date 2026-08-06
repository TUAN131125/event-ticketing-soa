import { useParams } from 'react-router-dom';
import { useAdminSession } from '../app/useAdminSession';
import { EventFormPage } from './EventFormPage';

export function ConnectedEventFormPage() {
  const { accessToken } = useAdminSession();
  const { eventId } = useParams();
  return <EventFormPage accessToken={accessToken} eventId={eventId} />;
}
