import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClientProvider, onlineManager } from '@tanstack/react-query';
import { createQueryClient } from '../src/app/query-client';
import { AuthProvider } from '../src/app/auth';
import { EventListPage } from '../src/pages/EventListPage';

const EVENT = {
  eventId: 'EV001',
  name: 'Dem nhac mua he',
  venue: 'Nha hat Thanh pho',
  startsAt: '2026-08-20T19:30:00Z',
  status: 'ON_SALE',
  ticketTypes: [{ code: 'VIP', name: 'VIP', price: { amountMinor: 1500000, currency: 'VND' } }],
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function renderEvents() {
  const client = createQueryClient();
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AuthProvider>
            <EventListPage />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
  return client;
}

const eventCalls = (fetchSpy: ReturnType<typeof vi.fn>) =>
  fetchSpy.mock.calls.filter(([url]) => String(url).includes('/api/events'));

describe('public event discovery', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    fetchSpy = vi.fn().mockResolvedValue(jsonResponse([EVENT]));
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    onlineManager.setOnline(true);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('calls the ESB while signed out', async () => {
    await renderEvents();
    await waitFor(() => expect(eventCalls(fetchSpy)).toHaveLength(1));
    const [url, init] = eventCalls(fetchSpy)[0] as [string, RequestInit];
    expect(url).toBe('http://esb.test/api/events');
    expect((init.headers as Headers).get('Authorization')).toBeNull();
    expect(await screen.findByText('Dem nhac mua he')).toBeInTheDocument();
  });

  it('calls fetch with a receiver the browser accepts', async () => {
    const receivers: unknown[] = [];
    fetchSpy.mockImplementation(function (this: unknown) {
      receivers.push(this);
      return Promise.resolve(jsonResponse([EVENT]));
    });
    await renderEvents();
    await waitFor(() => expect(receivers.length).toBeGreaterThan(0));
    for (const receiver of receivers) {
      expect(receiver === undefined || receiver === globalThis).toBe(true);
    }
  });

  it('still sends the request when online detection reports offline', async () => {
    onlineManager.setOnline(false);
    const client = await renderEvents();
    await waitFor(() => expect(eventCalls(fetchSpy)).toHaveLength(1));
    const query = client.getQueryCache().getAll()[0];
    expect(query.state.fetchStatus).not.toBe('paused');
    await waitFor(() => expect(query.state.status).toBe('success'));
    expect(screen.queryByText(/could not reach/i)).not.toBeInTheDocument();
  });

  it('does not report an unavailable service before a request has failed', async () => {
    let release: (value: Response) => void = () => undefined;
    fetchSpy.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    await renderEvents();
    expect(screen.queryByText(/could not reach/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument();
    await act(async () => {
      release(jsonResponse([EVENT]));
    });
    expect(await screen.findByText('Dem nhac mua he')).toBeInTheDocument();
  });

  // The shared client retries once, so the error state settles after a backoff delay and
  // needs more than the default assertion and test budgets.
  const untilError = { timeout: 8000 };
  const testBudget = 15000;

  it(
    'names the event service when the request really fails',
    async () => {
      fetchSpy.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));
      await renderEvents();
      expect(
        await screen.findByRole(
          'heading',
          { name: /could not reach the event service/i },
          untilError,
        ),
      ).toBeInTheDocument();
      expect(screen.queryByText(/booking service/i)).not.toBeInTheDocument();
    },
    testBudget,
  );

  it(
    'does not show an outage for a 4xx from the ESB',
    async () => {
      fetchSpy.mockImplementation(() =>
        Promise.resolve(
          jsonResponse(
            {
              correlationId: 'c',
              error: { code: 'BAD_REQUEST', message: 'bad', retryable: false },
            },
            400,
          ),
        ),
      );
      await renderEvents();
      expect(
        await screen.findByText(/something went wrong/i, undefined, untilError),
      ).toBeInTheDocument();
      expect(screen.queryByText(/could not reach/i)).not.toBeInTheDocument();
    },
    testBudget,
  );
});
