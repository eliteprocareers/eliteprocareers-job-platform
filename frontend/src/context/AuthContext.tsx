import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, setAuthToken, setActiveOrganizationHeader } from '../lib/api';
import type { LoginResponse, SignupResponse } from '../lib/types';

interface AuthContextValue {
  token: string | null;
  userId: string | null;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  // Returns the raw response so the caller can branch on
  // requires_confirmation -- signup() itself sets auth state only
  // when the API actually returned a usable session (i.e. this
  // Supabase project has email confirmation disabled). If
  // requires_confirmation is true, the account exists but nothing is
  // logged in yet -- the caller should send the person to /login,
  // not assume they're authenticated.
  signup: (email: string, password: string) => Promise<SignupResponse>;
  logout: () => void;
  isAuthenticated: boolean;
  // Multi-org (migration 0017): which org this session is acting as.
  // null means "no explicit choice" -- the backend then defaults to
  // the caller's oldest membership (api/dependencies.py), which is
  // exactly correct for the overwhelmingly common single-org case
  // and means most users never interact with this at all. Persisted
  // separately from the auth blob so switching orgs doesn't require
  // re-authenticating.
  activeOrganizationId: string | null;
  setActiveOrganizationId: (organizationId: string | null) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const STORAGE_KEY = 'eliteprocareers_auth';
const ACTIVE_ORG_STORAGE_KEY = 'eliteprocareers_active_org';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [activeOrganizationId, setActiveOrganizationIdState] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      setToken(parsed.access_token);
      setUserId(parsed.user_id);
      setEmail(parsed.email);
      setAuthToken(parsed.access_token);
    }
    const storedOrg = localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);
    if (storedOrg) {
      setActiveOrganizationIdState(storedOrg);
      setActiveOrganizationHeader(storedOrg);
    }
  }, []);

  function setActiveOrganizationId(organizationId: string | null) {
    setActiveOrganizationIdState(organizationId);
    setActiveOrganizationHeader(organizationId);
    if (organizationId) {
      localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, organizationId);
    } else {
      localStorage.removeItem(ACTIVE_ORG_STORAGE_KEY);
    }
  }

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
    // A fresh login doesn't know this account's orgs yet -- clear any
    // stale choice left over from a previous account on this browser
    // rather than risk sending a header naming an org this user isn't
    // in (harmless -- the backend 403s and falls back correctly -- but
    // pointless). Whoever's building on top of this can restore a
    // remembered org for *this* user id once org membership is loaded.
    setActiveOrganizationId(null);
  }

  async function signup(emailInput: string, password: string): Promise<SignupResponse> {
    const { data } = await api.post<SignupResponse>('/auth/signup', {
      email: emailInput,
      password,
    });
    if (data.access_token && data.refresh_token) {
      setToken(data.access_token);
      setUserId(data.user_id);
      setEmail(data.email);
      setAuthToken(data.access_token);
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          user_id: data.user_id,
          email: data.email,
        })
      );
      setActiveOrganizationId(null);
    }
    return data;
  }

  function logout() {
    setToken(null);
    setUserId(null);
    setEmail(null);
    setAuthToken(null);
    localStorage.removeItem(STORAGE_KEY);
    setActiveOrganizationId(null);
  }

  return (
    <AuthContext.Provider
      value={{
        token,
        userId,
        email,
        login,
        signup,
        logout,
        isAuthenticated: !!token,
        activeOrganizationId,
        setActiveOrganizationId,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
