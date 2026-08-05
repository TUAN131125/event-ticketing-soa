import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { authClient } from '../api/auth';
import type { AuthSession, Role, User } from '../types';

type AuthContextValue = {
  session: AuthSession | null;
  user: User | null;
  isRestoring: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  assignRole: (userId: string, role: Role, action: 'assign' | 'revoke') => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [isRestoring, setRestoring] = useState(true);

  useEffect(() => {
    let alive = true;
    authClient
      .refresh()
      .then((value) => {
        if (alive) setSession(value);
      })
      .catch(() => {
        /* first visit or expired cookie */
      })
      .finally(() => {
        if (alive) setRestoring(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setSession(await authClient.login({ email, password }));
  }, []);
  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    await authClient.register({ email, password, displayName });
  }, []);
  const logout = useCallback(async () => {
    const token = session?.accessToken;
    setSession(null);
    if (token) {
      try {
        await authClient.logout(token);
      } catch {
        /* local session remains cleared */
      }
    }
  }, [session?.accessToken]);
  const assignRole = useCallback(
    async (userId: string, role: Role, action: 'assign' | 'revoke') => {
      if (!session) throw new Error('You need to sign in again.');
      await authClient.assignRole(session.accessToken, userId, role, action);
    },
    [session],
  );
  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      isRestoring,
      isAuthenticated: Boolean(session),
      login,
      register,
      logout,
      assignRole,
    }),
    [assignRole, isRestoring, login, logout, register, session],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used within AuthProvider');
  return value;
}
