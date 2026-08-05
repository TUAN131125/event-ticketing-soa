import { request } from './http';
import type { AuthSession, TokenResponse, User } from '../types';

const identityBase = () => import.meta.env.VITE_IDENTITY_API_URL || '';
const csrfKey = 'event-ticketing.identity.csrf';

const readCsrf = (): string | null => {
  try {
    return sessionStorage.getItem(csrfKey);
  } catch {
    return null;
  }
};

const storeSession = (value: TokenResponse): AuthSession => {
  try {
    sessionStorage.setItem(csrfKey, value.csrfToken);
  } catch {
    /* the double-submit header is best effort in restricted storage modes */
  }
  return { accessToken: value.accessToken, expiresIn: value.expiresIn, user: value.user };
};

/**
 * Identity Service client for the operations console. Paths, payloads and headers follow
 * contracts/identity-service.yaml; nothing outside that document is called.
 */
export class AuthClient {
  private readonly base = identityBase();

  async register(input: { email: string; password: string }): Promise<User> {
    return request<User>(this.base, '/auth/register', {
      method: 'POST',
      body: input,
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
  }

  async login(input: { email: string; password: string }): Promise<AuthSession> {
    return storeSession(
      await request<TokenResponse>(this.base, '/auth/login', { method: 'POST', body: input }),
    );
  }

  async refresh(): Promise<AuthSession> {
    const csrf = readCsrf();
    if (!csrf) throw new Error('No active session to restore.');
    return storeSession(
      await request<TokenResponse>(this.base, '/auth/refresh', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf },
      }),
    );
  }

  async logout(): Promise<void> {
    const csrf = readCsrf();
    try {
      if (csrf)
        await request<void>(this.base, '/auth/logout', {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrf },
        });
    } finally {
      try {
        sessionStorage.removeItem(csrfKey);
      } catch {
        /* nothing to clear */
      }
    }
  }

  async me(accessToken: string): Promise<User> {
    return request<User>(this.base, '/auth/me', { accessToken });
  }
}

export const authClient = new AuthClient();
