import { ApiError, request } from './http';
import type { AuthSession, Role, User } from '../types';

const identityBase = () => import.meta.env.VITE_IDENTITY_API_URL || import.meta.env.VITE_ESB_API_URL || '';
const authPrefix = import.meta.env.VITE_AUTH_TRANSPORT === 'gateway' ? '/auth' : '/auth';
const csrfKey = 'event-ticketing.identity.csrf';

type RawUser = { id?: string; userId?: string; email: string; displayName?: string; roles?: Role[]; role?: Role; status?: string };
const mapUser = (value: RawUser): User => ({ id: value.id ?? value.userId ?? '', email: value.email, displayName: value.displayName, roles: value.roles ?? (value.role ? [value.role] : []), status: value.status });

type AuthPayload = { accessToken?: string; access_token?: string; token?: string; csrfToken?: string; user?: RawUser; expiresAt?: string };
const mapSession = (value: AuthPayload): AuthSession => {
  const accessToken = value.accessToken ?? value.access_token ?? value.token;
  if (!accessToken || !value.user) throw new ApiError('Authentication response was incomplete', { code: 'INVALID_AUTH_RESPONSE' });
  if (value.csrfToken) sessionStorage.setItem(csrfKey, value.csrfToken);
  return { accessToken, user: mapUser(value.user), expiresAt: value.expiresAt };
};

export class AuthClient {
  private readonly base = identityBase();
  async register(input: { email: string; password: string; displayName?: string }): Promise<void> {
    await request(this.base, `${authPrefix}/register`, { method: 'POST', body: input });
  }
  async login(input: { email: string; password: string }): Promise<AuthSession> {
    return mapSession(await request<AuthPayload>(this.base, `${authPrefix}/login`, { method: 'POST', body: input }));
  }
  async refresh(): Promise<AuthSession> {
    const csrf = sessionStorage.getItem(csrfKey);
    return mapSession(await request<AuthPayload>(this.base, `${authPrefix}/refresh`, { method: 'POST', body: {}, headers: csrf ? { 'X-CSRF-Token': csrf } : undefined }));
  }
  async logout(accessToken: string): Promise<void> {
    const csrf = sessionStorage.getItem(csrfKey);
    await request(this.base, `${authPrefix}/logout`, { method: 'POST', body: {}, accessToken, headers: csrf ? { 'X-CSRF-Token': csrf } : undefined });
    sessionStorage.removeItem(csrfKey);
  }
  async me(accessToken: string): Promise<User> {
    const payload = await request<RawUser>(this.base, `${authPrefix}/me`, { accessToken });
    return mapUser(payload);
  }
  async assignRole(accessToken: string, userId: string, role: Role, action: 'assign' | 'revoke'): Promise<void> {
    await request(this.base, `/admin/users/${encodeURIComponent(userId)}/roles`, { method: 'POST', body: { role, action: action.toUpperCase() }, accessToken });
  }
}

export const authClient = new AuthClient();
