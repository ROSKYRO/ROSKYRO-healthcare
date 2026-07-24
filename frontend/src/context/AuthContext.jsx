import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import api, { setToken, getToken } from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadPillars = useCallback(async (baseUser) => {
    if (!baseUser || baseUser.appShell !== 'customer') return baseUser;
    try {
      const { data } = await api.get('/plans/mine');
      return { ...baseUser, activePillars: data.activePillars, monthlyTotal: data.monthlyTotal };
    } catch {
      return { ...baseUser, activePillars: [], monthlyTotal: 0 };
    }
  }, []);

  const loadMe = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get('/auth/me');
      const withPillars = await loadPillars(data.user);
      setUser(withPillars);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [loadPillars]);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  async function login(identifier, password) {
    const { data } = await api.post('/auth/login', { identifier, password });
    setToken(data.token);
    const withPillars = await loadPillars(data.user);
    setUser(withPillars);
    return withPillars;
  }

  async function register(payload) {
    const { data } = await api.post('/auth/register', payload);
    setToken(data.token);
    const withPillars = await loadPillars(data.user);
    setUser(withPillars);
    return withPillars;
  }

  async function refreshPillars() {
    setUser((u) => u);
    const { data } = await api.get('/plans/mine');
    setUser((u) => (u ? { ...u, activePillars: data.activePillars, monthlyTotal: data.monthlyTotal } : u));
  }

  function logout() {
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh: loadMe, refreshPillars }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
