import axios from 'axios';

// Split deployment (Vercel frontend + Railway backend, separate origins) --
// REACT_APP_API_URL must be set at BUILD time on Vercel (CRA/CRACO only
// embeds env vars prefixed REACT_APP_ into the bundle, and only the value
// present when `npm run build` ran -- setting it later in the Vercel
// dashboard without a rebuild has no effect). Example:
// https://roskyro-backend.up.railway.app/api
//
// Falls back to the relative '/api' path when unset, which only matters
// for local dev: CRA/CRACO's dev server "proxy" field (package.json)
// forwards that to http://localhost:8000, so `npm start` still works
// against a local backend with zero extra config.
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = localStorageSafeGet('roskyro_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// NOTE: browser localStorage is used here (client app only, not a Claude
// artifact) purely to persist the demo session across page reloads.
function localStorageSafeGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) window.localStorage.setItem('roskyro_token', token);
    else window.localStorage.removeItem('roskyro_token');
  } catch {
    /* no-op */
  }
}

export function getToken() {
  return localStorageSafeGet('roskyro_token');
}

export default api;
