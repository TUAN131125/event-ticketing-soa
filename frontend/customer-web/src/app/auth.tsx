import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { AuthClient, type User } from '../api/auth-client';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  client: AuthClient;
  signIn: (email: string, password: string) => Promise<User>;
  signUp: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
  refresh: () => Promise<User | null>;
}
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useMemo(() => new AuthClient(), []);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const restore = async () => {
    setLoading(true);
    const current = await client.restore();
    setUser(current);
    setLoading(false);
    return current;
  };
  useEffect(() => {
    void restore();
  }, []);
  const value: AuthContextValue = {
    user,
    loading,
    client,
    signIn: async (email, password) => {
      const result = await client.login(email, password);
      setUser(result.user);
      return result.user;
    },
    signUp: async (email, password) => {
      const result = await client.register(email, password);
      return result;
    },
    signOut: async () => {
      await client.logout();
      setUser(null);
    },
    refresh: restore,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
