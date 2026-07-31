import { RefreshCcw } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button, ErrorState, ServiceUnavailableState, Spinner } from '@event-ticketing/shared-ui';
import { ApiError } from '../api/http';
import { isUnavailable } from '../api/esb';

export function QueryState({ isLoading, error, onRetry, children }: { isLoading: boolean; error: unknown; onRetry: () => void; children: ReactNode }) {
  if (isLoading) return <div className="query-loading"><Spinner label="Loading data" /></div>;
  if (error) {
    const apiError = error instanceof ApiError ? error : undefined;
    if (isUnavailable(error)) return <ServiceUnavailableState title="Service unavailable" description="The gateway is not ready yet. No placeholder data is shown." action={<Button icon={<RefreshCcw size={16} />} onClick={onRetry}>Try again</Button>} />;
    if (apiError?.status === 401) return <ErrorState title="Session expired" description="Sign in again to continue." action={<Button onClick={() => { window.location.href = '/login'; }}>Sign in</Button>} />;
    if (apiError?.status === 403) return <ErrorState title="Forbidden" description="Your account cannot access this operation." />;
    if (apiError?.status === 404) return <ErrorState title="Not found" description="The requested resource does not exist." />;
    return <ErrorState title="Could not load this view" description={apiError?.message ?? 'Try again in a moment.'} action={<Button icon={<RefreshCcw size={16} />} onClick={onRetry}>Retry</Button>} />;
  }
  return <>{children}</>;
}
