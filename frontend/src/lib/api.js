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

// Fixed: there was no response interceptor at all -- the JWT is long-lived
// (JWT_EXPIRES_DAYS=7, backend/app/config.py) with no refresh mechanism,
// and AuthContext's `user` state is only ever populated once on mount
// (loadMe() in a plain useEffect). So once a token actually expired, or an
// admin deactivated the account mid-session, EVERY subsequent request
// failed with a 401 from get_current_user (app/auth.py: "Missing
// authorization token." / "Invalid or expired token." / "User not
// found.") -- but nothing ever cleared the stale `user` object or sent the
// person back to /login. They'd sit on a fully-rendered authenticated
// screen with every data fetch silently failing, with no way back to
// /login short of manually clicking "Sign out." Scoped to 401 only (not
// 403): a 403 from require_roles/require_internal is a legitimate
// "you don't have permission for THIS action" response on an otherwise
// valid session and must not force a full logout.
let onSessionExpired = null;
export function setSessionExpiredHandler(handler) {
  onSessionExpired = handler;
}
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && onSessionExpired) {
      onSessionExpired();
    }
    return Promise.reject(error);
  },
);

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
