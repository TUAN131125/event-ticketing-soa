import type { components } from '@event-ticketing/shared-ui/identity-contract';

export type Role = components['schemas']['Role'];
export type User = components['schemas']['User'];
export type TokenResponse = components['schemas']['TokenResponse'];
export type UserStatus = User['status'];
type ContractErrorResponse = components['schemas']['ErrorResponse'];

/** A wire error as far as it can be trusted: any field may be missing on a bad response. */
export type AuthErrorPayload = {
  correlationId?: string;
  traceId?: string;
  error?: Partial<ContractErrorResponse['error']>;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly correlationId?: string;
  readonly traceId?: string;

  constructor(
    status: number,
    payload: AuthErrorPayload | undefined,
    fallback = 'Request failed',
    // Keeping the original throw attached stops a programming error inside the request
    // path from being indistinguishable from a genuine transport failure.
    options?: { cause?: unknown },
  ) {
    super(payload?.error?.message ?? fallback, options);
    this.name = 'ApiError';
    this.status = status;
    this.code =
      payload?.error?.code ??
      (status === 401 ? 'UNAUTHENTICATED' : status === 403 ? 'FORBIDDEN' : 'REQUEST_FAILED');
    this.retryable = payload?.error?.retryable ?? status >= 500;
    this.correlationId = payload?.correlationId;
    this.traceId = payload?.traceId;
  }
}

export interface AuthClientOptions {
  identityApiUrl?: string;
  fetchImpl?: typeof fetch;
}

const csrfStorageKey = 'evently.csrfToken';

function readJson(value: unknown): AuthErrorPayload | undefined {
  return value && typeof value === 'object' ? (value as AuthErrorPayload) : undefined;
}

/**
 * Identity Service client. The browser talks to Identity only for authentication; every
 * business operation goes through the ESB. Paths, headers and payloads follow
 * contracts/identity-service.yaml.
 */
export class AuthClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private accessToken: string | null = null;
  private refreshPromise: Promise<TokenResponse> | null = null;

  constructor(options: AuthClientOptions = {}) {
    this.baseUrl = (options.identityApiUrl ?? import.meta.env.VITE_IDENTITY_API_URL ?? '').replace(
      /\/$/,
      '',
    );
    // `fetch` must be called with the global as its receiver. Storing the bare function on
    // the instance and calling `this.fetchImpl(...)` makes the receiver this client, which
    // browsers reject with "Illegal invocation" before any request is sent. The wrapper also
    // keeps the lookup late so a replaced global is honoured.
    this.fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  }

  get token(): string | null {
    return this.accessToken;
  }

  private csrfToken(): string | null {
    try {
      return sessionStorage.getItem(csrfStorageKey);
    } catch {
      return null;
    }
  }

  private async request<T>(path: string, init: RequestInit = {}, retryOn401 = true): Promise<T> {
    // A missing build-time URL is a deployment defect, not an unavailable service.
    if (!this.baseUrl)
      throw new ApiError(0, {
        error: {
          code: 'CONFIGURATION_ERROR',
          message: 'This build has no Identity URL configured.',
          retryable: false,
        },
      });
    const headers = new Headers(init.headers);
    headers.set('Accept', 'application/json');
    headers.set('X-Correlation-ID', crypto.randomUUID());
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    if (this.accessToken && !headers.has('Authorization'))
      headers.set('Authorization', `Bearer ${this.accessToken}`);
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: 'include',
      });
    } catch (cause) {
      throw new ApiError(
        503,
        {
          error: {
            code: 'SERVICE_UNAVAILABLE',
            message: 'Authentication service is temporarily unavailable.',
            retryable: true,
          },
        },
        'Authentication service is temporarily unavailable.',
        { cause },
      );
    }
    if (
      response.status === 401 &&
      retryOn401 &&
      !path.endsWith('/refresh') &&
      !path.endsWith('/login')
    ) {
      try {
        await this.refresh();
        return this.request<T>(path, init, false);
      } catch {
        this.clearSession();
      }
    }
    if (!response.ok) {
      let payload: AuthErrorPayload | undefined;
      try {
        payload = readJson(await response.json());
      } catch {
        /* response may be empty */
      }
      throw new ApiError(response.status, payload);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  private storeSession(result: TokenResponse): TokenResponse {
    this.accessToken = result.accessToken;
    try {
      sessionStorage.setItem(csrfStorageKey, result.csrfToken);
    } catch {
      /* the double-submit header is best effort in restricted storage modes */
    }
    return result;
  }

  clearSession(): void {
    this.accessToken = null;
    try {
      sessionStorage.removeItem(csrfStorageKey);
    } catch {
      /* nothing to clear */
    }
  }

  /** POST /auth/register — the contract declares Idempotency-Key as required. */
  async register(email: string, password: string): Promise<User> {
    return this.request<User>(
      '/auth/register',
      {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      },
      false,
    );
  }

  /** POST /auth/login — sets the refresh and CSRF cookies and returns the access token. */
  async login(email: string, password: string): Promise<TokenResponse> {
    return this.storeSession(
      await this.request<TokenResponse>(
        '/auth/login',
        { method: 'POST', body: JSON.stringify({ email: email.trim().toLowerCase(), password }) },
        false,
      ),
    );
  }

  /** POST /auth/refresh — double-submit CSRF header plus the HttpOnly refresh cookie. */
  async refresh(): Promise<TokenResponse> {
    if (this.refreshPromise) return this.refreshPromise;
    const csrf = this.csrfToken();
    if (!csrf) {
      return Promise.reject(
        new ApiError(401, {
          error: { code: 'UNAUTHENTICATED', message: 'No active session.', retryable: false },
        }),
      );
    }
    this.refreshPromise = this.request<TokenResponse>(
      '/auth/refresh',
      { method: 'POST', headers: { 'X-CSRF-Token': csrf } },
      false,
    )
      .then((result) => this.storeSession(result))
      .finally(() => {
        this.refreshPromise = null;
      });
    return this.refreshPromise;
  }

  async restore(): Promise<User | null> {
    try {
      const result = await this.refresh();
      return result.user;
    } catch {
      this.clearSession();
      return null;
    }
  }

  /** GET /auth/me */
  async me(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  /** POST /auth/logout — 204, clears the refresh and CSRF cookies. */
  async logout(): Promise<void> {
    const csrf = this.csrfToken();
    try {
      if (csrf) {
        await this.request<void>(
          '/auth/logout',
          { method: 'POST', headers: { 'X-CSRF-Token': csrf } },
          false,
        );
      }
    } finally {
      this.clearSession();
    }
  }
}
