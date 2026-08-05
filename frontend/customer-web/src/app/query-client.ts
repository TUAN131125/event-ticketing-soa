import { QueryClient } from '@tanstack/react-query';

/**
 * The single React Query configuration for this application.
 *
 * This app has no offline mode. React Query's default network mode parks queries and
 * mutations in `fetchStatus: "paused"` whenever the browser's online detection reports
 * offline, so the request is never attempted and the UI cannot tell "not sent" apart from
 * "failed". `always` makes every request be attempted and lets a real transport failure
 * surface as an error instead.
 *
 * Pages must not override this; they use the client provided by `App`.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 1, refetchOnWindowFocus: false, networkMode: 'always' },
      mutations: { networkMode: 'always' },
    },
  });
}
