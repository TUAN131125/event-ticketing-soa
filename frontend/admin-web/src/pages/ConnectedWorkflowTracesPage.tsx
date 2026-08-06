import { useAdminSession } from '../app/useAdminSession';
import { WorkflowTracesPage } from './WorkflowTracesPage';

export function ConnectedWorkflowTracesPage() {
  const { accessToken } = useAdminSession();
  return <WorkflowTracesPage accessToken={accessToken} />;
}
