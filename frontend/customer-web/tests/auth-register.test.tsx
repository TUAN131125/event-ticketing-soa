import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../src/app/auth';
import { RegisterPage } from '../src/pages/AuthPages';

const VALID_EMAIL = 'new-user@example.com';
const VALID_PASSWORD = 'Sup3rSecretPass!42';

function jsonResponse(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const errorBody = (code: string, message: string, retryable = false) => ({
  correlationId: 'corr-test-0001',
  error: { code, message, retryable },
});

async function renderRegister() {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={['/register']}>
        <AuthProvider>
          <RegisterPage />
        </AuthProvider>
      </MemoryRouter>,
    );
  });
}

async function fillAndSubmit(email = VALID_EMAIL, password = VALID_PASSWORD) {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } });
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
}

const registerCalls = (fetchSpy: ReturnType<typeof vi.fn>) =>
  fetchSpy.mock.calls.filter(([url]) => String(url).includes('/auth/register'));

describe('customer registration', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          userId: '00000000-0000-4000-8000-000000000001',
          email: VALID_EMAIL,
          status: 'ACTIVE',
          roles: ['CUSTOMER'],
          tokenVersion: 1,
          createdAt: '2026-08-05T00:00:00Z',
        },
        201,
      ),
    );
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('submits the form and calls Identity exactly once', async () => {
    await renderRegister();
    await fillAndSubmit();
    await waitFor(() => expect(registerCalls(fetchSpy)).toHaveLength(1));
    const [url, init] = registerCalls(fetchSpy)[0] as [string, RequestInit];
    expect(url).toBe('http://identity.test/auth/register');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      email: VALID_EMAIL,
      password: VALID_PASSWORD,
    });
    expect((init.headers as Headers).get('Idempotency-Key')).toBeTruthy();
  });

  it('calls fetch with a receiver the browser accepts', async () => {
    // Browsers reject `fetch` invoked with a non-global receiver ("Illegal invocation"),
    // which fails before any request is sent. jsdom does not enforce that rule, so the
    // invariant is asserted here directly.
    const receivers: unknown[] = [];
    fetchSpy.mockImplementation(function (this: unknown) {
      receivers.push(this);
      return Promise.resolve(jsonResponse({ userId: 'u', email: VALID_EMAIL }, 201));
    });
    await renderRegister();
    await fillAndSubmit();
    await waitFor(() => expect(receivers.length).toBeGreaterThan(0));
    for (const receiver of receivers) {
      expect(receiver === undefined || receiver === globalThis).toBe(true);
    }
  });

  it('shows field errors and sends no request when validation fails', async () => {
    await renderRegister();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'not-an-email' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'short' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Enter a valid email')).toBeInTheDocument();
    expect(await screen.findByText('Use at least 12 characters')).toBeInTheDocument();
    expect(registerCalls(fetchSpy)).toHaveLength(0);
    expect(screen.queryByText(/temporarily unavailable/i)).not.toBeInTheDocument();
  });

  it('reports a 409 as an existing account, not an outage', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse(errorBody('EMAIL_ALREADY_REGISTERED', 'Email already registered'), 409),
    );
    await renderRegister();
    await fillAndSubmit();
    expect(await screen.findByText(/already registered/i)).toBeInTheDocument();
    expect(screen.queryByText(/temporarily unavailable/i)).not.toBeInTheDocument();
  });

  it('reports a 422 as invalid data, not an outage', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse(errorBody('VALIDATION_ERROR', 'Password does not meet the policy'), 422),
    );
    await renderRegister();
    await fillAndSubmit();
    expect(await screen.findByText(/does not meet the policy/i)).toBeInTheDocument();
    expect(screen.queryByText(/temporarily unavailable/i)).not.toBeInTheDocument();
  });

  it('reports a 5xx as an unavailable service', async () => {
    fetchSpy.mockResolvedValue(jsonResponse(errorBody('INTERNAL_ERROR', 'boom', true), 503));
    await renderRegister();
    await fillAndSubmit();
    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
  });

  it('reports a transport failure as an unavailable service', async () => {
    fetchSpy.mockRejectedValue(new TypeError('Failed to fetch'));
    await renderRegister();
    await fillAndSubmit();
    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
  });
});
