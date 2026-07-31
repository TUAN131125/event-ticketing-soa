import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../src/app/auth';
import { EventListPage } from '../src/pages/EventListPage';

describe('customer discovery', () => {
  it('shows a service unavailable state instead of fake events', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('offline'));
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><AuthProvider><EventListPage /></AuthProvider></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText(/event services are unavailable|sign in to continue/i)).toBeInTheDocument();
    expect(screen.queryByText(/Summer/i)).not.toBeInTheDocument();
    fetcher.mockRestore();
  });
});
