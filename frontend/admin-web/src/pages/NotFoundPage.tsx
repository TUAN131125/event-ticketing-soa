import { useNavigate } from 'react-router-dom';
import { Button, NotFoundState } from '@event-ticketing/shared-ui';
export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div className="centered-state">
      <NotFoundState
        title="Page not found"
        description="That operations page does not exist."
        action={<Button onClick={() => navigate('/')}>Back to overview</Button>}
      />
    </div>
  );
}
