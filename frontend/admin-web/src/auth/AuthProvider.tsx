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
import type { AuthSession, User } from '../types';

type AuthContextValue = {
  session: AuthSession | null;
  user: User | null;
  isRestoring: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
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
  const logout = useCallback(async () => {
    setSession(null);
    try {
      await authClient.logout();
    } catch {
      /* local session remains cleared */
    }
  }, []);
  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      isRestoring,
      isAuthenticated: Boolean(session),
      login,
      logout,
    }),
    [isRestoring, login, logout, session],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used within AuthProvider');
  return value;
}
