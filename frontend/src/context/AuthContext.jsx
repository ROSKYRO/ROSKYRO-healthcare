import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import api, { setToken, getToken } from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Business (customer) and partner accounts each have their own
  // pillar-subscription catalog/endpoint (see routers/plans.py vs
  // routers/partner_plans.py) -- pick the right one by appShell so both
  // sides get a real activePillars/monthlyTotal on the user object.
  const loadPillars = useCallback(async (baseUser) => {
    if (!baseUser || (baseUser.appShell !== 'customer' && baseUser.appShell !== 'partner')) return baseUser;
    const endpoint = baseUser.appShell === 'partner' ? '/partner-plans/mine' : '/plans/mine';
    try {
      const { data } = await api.get(endpoint);
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
    // Swallow errors here rather than letting them propagate -- this is
    // always called right AFTER a subscribe/cancel API call has already
    // succeeded, just to refresh the cached activePillars/monthlyTotal on
    // the user object. If this refresh itself hiccups (transient network
    // blip), the caller's try/catch would otherwise wrongly tell the user
    // "could not activate this plan" even though the plan change already
    // went through -- only the local cache refresh failed. Worst case here
    // is a stale pillar badge until the next page load/refresh.
    try {
      const endpoint = user?.appShell === 'partner' ? '/partner-plans/mine' : '/plans/mine';
      const { data } = await api.get(endpoint);
      setUser((u) => (u ? { ...u, activePillars: data.activePillars, monthlyTotal: data.monthlyTotal } : u));
    } catch {
      // Best-effort refresh only -- see comment above.
    }
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
