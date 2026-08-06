import { useAdminSession } from '../app/useAdminSession';
import { OverviewPage } from './OverviewPage';

export function ConnectedOverviewPage() {
  const { accessToken } = useAdminSession();
  return <OverviewPage accessToken={accessToken} />;
}
