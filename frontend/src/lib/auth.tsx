'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authAPI } from '@/lib/api';

interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  department: string | null;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  loading: true,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Check for existing token on mount (client-side only)
  useEffect(() => {
    const stored = localStorage.getItem('astra_token');
    if (stored) {
      setToken(stored);
      authAPI
        .me()
        .then((res) => {
          setUser(res.data);
        })
        .catch(() => {
          localStorage.removeItem('astra_token');
          setToken(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (username: string, password: string) => {
    const res = await authAPI.login(username, password);
    const newToken = res.data.access_token;
    localStorage.setItem('astra_token', newToken);
    setToken(newToken);

    const meRes = await authAPI.me();
    setUser(meRes.data);
  };

  const logout = () => {
    localStorage.removeItem('astra_token');
    localStorage.removeItem('astra_project_id');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
