import { render, screen } from '@testing-library/react';
import { QueryState } from '../../src/components/QueryState';

describe('QueryState', () => {
  it('renders unavailable copy without fake data', () => {
    render(<QueryState isLoading={false} error={new Error('service unavailable')} onRetry={() => undefined}><p>data</p></QueryState>);
    expect(screen.getByText(/could not load/i)).toBeInTheDocument();
    expect(screen.queryByText('data')).not.toBeInTheDocument();
  });
});
