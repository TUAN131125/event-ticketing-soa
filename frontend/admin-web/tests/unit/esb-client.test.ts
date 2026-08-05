import { EsbAdminClient } from '../../src/api/esb';

describe('admin ESB client', () => {
  it('queries only the canonical public event collection', async () => {
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      );
    const client = new EsbAdminClient('http://esb.test');
    await client.events('admin-jwt');
    expect(fetcher.mock.calls[0]?.[0]).toMatch(/\/api\/events$/);
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe(
      'Bearer admin-jwt',
    );
  });
});
