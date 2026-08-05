import { Navigate, useLocation } from 'react-router-dom';
import { ForbiddenState, Spinner } from '@event-ticketing/shared-ui';
import { useAuth } from './auth';

export function RequireAuth({ children, roles }: { children: React.ReactNode; roles?: string[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading)
    return (
      <div className="page-state">
        <Spinner label="Restoring your session" />
      </div>
    );
  if (!user)
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (roles && !roles.some((role) => user.roles.includes(role)))
    return (
      <ForbiddenState
        title="This area is restricted"
        description="Your account does not have permission to view this page."
      />
    );
  return <>{children}</>;
}
