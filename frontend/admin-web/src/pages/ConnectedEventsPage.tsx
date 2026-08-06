import { useAdminSession } from '../app/useAdminSession';
import { EventsPage } from './EventsPage';

export function ConnectedEventsPage() {
  const { accessToken } = useAdminSession();
  return <EventsPage accessToken={accessToken} />;
}
