import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { api, setAuthToken } from '../lib/api';
import type { LoginResponse } from '../lib/types';

interface AuthContextValue {
  token: string | null;
  userId: string | null;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const STORAGE_KEY = 'eliteprocareers_auth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      setToken(parsed.access_token);
      setUserId(parsed.user_id);
      setEmail(parsed.email);
      setAuthToken(parsed.access_token);
    }
  }, []);

  async function login(emailInput: string, password: string) {
    const { data } = await api.post<LoginResponse>('/auth/login', {
      email: emailInput,
      password,
    });
    setToken(data.access_token);
    setUserId(data.user_id);
    setEmail(data.email);
    setAuthToken(data.access_token);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }

  function logout() {
    setToken(null);
    setUserId(null);
    setEmail(null);
    setAuthToken(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  return (
    <AuthContext.Provider value={{ token, userId, email, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
