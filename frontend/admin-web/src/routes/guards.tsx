import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { ForbiddenState, Spinner, UnauthorizedState } from '@event-ticketing/shared-ui';
import { useAuth } from '../auth/AuthProvider';

export function ProtectedRoute({ roles = [] }: { roles?: string[] }) {
  const { isAuthenticated, isRestoring, user } = useAuth();
  const location = useLocation();
  if (isRestoring)
    return (
      <div className="route-loading">
        <Spinner label="Restoring your session" />
      </div>
    );
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles.length > 0 && !roles.some((role) => user?.roles.includes(role)))
    return (
      <ForbiddenState
        title="Admin access required"
        description="Your account does not have an operations role for this area."
      />
    );
  return <Outlet />;
}

export function LoginOnlyRoute() {
  const { isAuthenticated, isRestoring } = useAuth();
  if (isRestoring)
    return (
      <div className="route-loading">
        <Spinner label="Checking session" />
      </div>
    );
  return isAuthenticated ? <Navigate to="/" replace /> : <Outlet />;
}

export function InlineAuthState({ forbidden = false }: { forbidden?: boolean }) {
  return forbidden ? (
    <ForbiddenState
      title="Forbidden"
      description="You do not have permission to view this resource."
    />
  ) : (
    <UnauthorizedState
      title="Sign in required"
      description="Your session is no longer valid. Sign in to continue."
    />
  );
}
