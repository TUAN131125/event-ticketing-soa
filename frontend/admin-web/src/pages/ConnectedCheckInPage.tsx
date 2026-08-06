import { useAdminSession } from '../app/useAdminSession';
import { CheckInPage } from './CheckInPage';

export function ConnectedCheckInPage() {
  const { accessToken } = useAdminSession();
  return <CheckInPage accessToken={accessToken} />;
}
