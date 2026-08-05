export type Role = 'CUSTOMER' | 'ADMIN' | 'CHECKIN_STAFF' | 'SERVICE' | string;
export type UserStatus = 'ACTIVE' | 'DISABLED' | string;

export interface User {
  userId: string;
  email: string;
  status: UserStatus;
  roles: Role[];
  tokenVersion: number;
  createdAt: string;
}

export interface TokenResponse {
  accessToken: string;
  tokenType: 'Bearer' | string;
  expiresIn: number;
  csrfToken: string;
  user: User;
}

export interface AuthErrorPayload {
  correlationId?: string;
  traceId?: string;
  error?: {
    code?: string;
    message?: string;
    retryable?: boolean;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly correlationId?: string;
  readonly traceId?: string;

  constructor(status: number, payload: AuthErrorPayload | undefined, fallback = 'Request failed') {
    super(payload?.error?.message ?? fallback);
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

type AuthTransport = 'direct' | 'gateway';

export interface AuthClientOptions {
  identityApiUrl?: string;
  esbApiUrl?: string;
  transport?: AuthTransport;
  fetchImpl?: typeof fetch;
}

function readJson(value: unknown): AuthErrorPayload | undefined {
  return value && typeof value === 'object' ? (value as AuthErrorPayload) : undefined;
}

function normaliseUrl(value: string): string {
  return value.replace(/\/$/, '');
}

export class AuthClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private accessToken: string | null = null;
  private refreshPromise: Promise<TokenResponse> | null = null;

  constructor(options: AuthClientOptions = {}) {
    const transport =
      options.transport ??
      (import.meta.env.VITE_AUTH_TRANSPORT as AuthTransport | undefined) ??
      'direct';
    const identityUrl = options.identityApiUrl ?? import.meta.env.VITE_IDENTITY_API_URL ?? '';
    const esbUrl = options.esbApiUrl ?? import.meta.env.VITE_ESB_API_URL ?? '';
    this.baseUrl = normaliseUrl(transport === 'gateway' ? esbUrl : identityUrl);
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  get token(): string | null {
    return this.accessToken;
  }

  private csrfToken(): string | undefined {
    return sessionStorage.getItem('evently.csrfToken') ?? undefined;
  }

  private async request<T>(path: string, init: RequestInit = {}, retryOn401 = true): Promise<T> {
    if (!this.baseUrl)
      throw new ApiError(503, {
        error: {
          code: 'SERVICE_UNAVAILABLE',
          message: 'Identity service is not configured.',
          retryable: true,
        },
      });
    const headers = new Headers(init.headers);
    headers.set('Accept', 'application/json');
    headers.set('X-Correlation-ID', crypto.randomUUID());
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    if (this.accessToken && !headers.has('Authorization'))
      headers.set('Authorization', `Bearer ${this.accessToken}`);
    if ((path.endsWith('/refresh') || path.endsWith('/logout')) && this.csrfToken())
      headers.set('X-CSRF-Token', this.csrfToken() as string);
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: 'include',
      });
    } catch {
      throw new ApiError(503, {
        error: {
          code: 'SERVICE_UNAVAILABLE',
          message: 'Authentication service is temporarily unavailable.',
          retryable: true,
        },
      });
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
    sessionStorage.setItem('evently.csrfToken', result.csrfToken);
    return result;
  }

  clearSession(): void {
    this.accessToken = null;
    sessionStorage.removeItem('evently.csrfToken');
  }

  async register(email: string, password: string): Promise<User> {
    return this.request<User>(
      '/auth/register',
      { method: 'POST', body: JSON.stringify({ email: email.trim().toLowerCase(), password }) },
      false,
    );
  }

  async login(email: string, password: string): Promise<TokenResponse> {
    return this.storeSession(
      await this.request<TokenResponse>(
        '/auth/login',
        { method: 'POST', body: JSON.stringify({ email: email.trim().toLowerCase(), password }) },
        false,
      ),
    );
  }

  async refresh(): Promise<TokenResponse> {
    if (this.refreshPromise) return this.refreshPromise;
    this.refreshPromise = this.request<TokenResponse>('/auth/refresh', { method: 'POST' }, false)
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

  async me(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  async logout(): Promise<void> {
    try {
      await this.request<void>('/auth/logout', { method: 'POST' }, false);
    } finally {
      this.clearSession();
    }
  }

  async changeRole(userId: string, role: Role, action: 'ASSIGN' | 'REVOKE'): Promise<unknown> {
    return this.request(`/admin/users/${encodeURIComponent(userId)}/roles`, {
      method: 'POST',
      body: JSON.stringify({ role, action }),
    });
  }
}
