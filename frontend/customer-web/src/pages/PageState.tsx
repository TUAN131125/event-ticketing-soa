import { Link } from 'react-router-dom';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { ApiError } from '../api/auth-client';
import {
  Button,
  ErrorState,
  ForbiddenState,
  NotFoundState,
  ServiceUnavailableState,
  Spinner,
  UnauthorizedState,
} from '@event-ticketing/shared-ui';

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="page-state">
      <Spinner label={label} />
    </div>
  );
}
export function QueryState({
  error,
  retry,
  notFound = false,
}: {
  error: unknown;
  retry: () => void;
  notFound?: boolean;
}) {
  const api = error instanceof ApiError ? error : null;
  if (notFound || api?.status === 404 || api?.code === 'NOT_FOUND')
    return (
      <NotFoundState
        title="We could not find that"
        description="The event or booking may have been removed or the link is out of date."
      />
    );
  if (api?.status === 401 || api?.code === 'UNAUTHENTICATED')
    return (
      <UnauthorizedState
        title="Sign in to continue"
        description="Your session has expired. Please sign in again."
        action={
          <Link to="/login" className="button button-primary">
            Sign in
          </Link>
        }
      />
    );
  if (api?.status === 403 || api?.code === 'FORBIDDEN')
    return (
      <ForbiddenState
        title="You do not have access"
        description="This content is only available to the account that made the booking."
      />
    );
  if (api?.status === 503 || api?.retryable || api?.code === 'SERVICE_UNAVAILABLE')
    return (
      <ServiceUnavailableState
        title="Event services are unavailable"
        description="We could not reach the booking service. Try again in a moment."
        action={
          <Button onClick={retry}>
            <RefreshCw size={16} /> Retry
          </Button>
        }
      />
    );
  return (
    <ErrorState
      title="Something went wrong"
      description={api?.message ?? 'Please try again.'}
      action={
        <Button variant="secondary" onClick={retry}>
          <AlertCircle size={16} /> Try again
        </Button>
      }
    />
  );
}
