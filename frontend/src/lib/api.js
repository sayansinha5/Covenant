import axios from 'axios';

const CSRF_HEADERS = { 'X-Requested-With': 'covenant' };
const NETWORK_MESSAGE = "Can't reach Covenant. Check that the API is running and try again.";
const FALLBACK_MESSAGE = 'Something went wrong. Try again.';

let accessToken = null;
let refreshing = null;
let handlers = { onRefreshed: () => {}, onExpired: () => {} };

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  withCredentials: true,
  timeout: 30_000,
});

export function setAccessToken(token) {
  accessToken = token;
}

export function setSessionHandlers(next) {
  handlers = { ...handlers, ...next };
}

/** One refresh at a time: concurrent callers share the same request, because a refresh token
 * can only be used once (a second use would look like theft and revoke the session). */
export function refreshSession() {
  refreshing ??= api
    .post('/auth/refresh', null, { headers: CSRF_HEADERS, skipAuthRefresh: true })
    .then(({ data }) => {
      accessToken = data.access_token;
      handlers.onRefreshed(data);
      return data;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export async function endSession() {
  try {
    await api.post('/auth/logout', null, { headers: CSRF_HEADERS, skipAuthRefresh: true });
  } finally {
    accessToken = null;
  }
}

api.interceptors.request.use((config) => {
  config.headers['X-Request-ID'] = crypto.randomUUID();
  if (accessToken && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  config.sentToken = accessToken;
  return config;
});

api.interceptors.response.use(undefined, async (error) => {
  const { config, response } = error;
  if (response?.status !== 401 || !config || config.skipAuthRefresh || config.retried) {
    throw error;
  }
  config.retried = true;
  // Another request may already have refreshed while this one was in flight.
  if (!accessToken || accessToken === config.sentToken) {
    try {
      await refreshSession();
    } catch {
      accessToken = null;
      handlers.onExpired();
      throw error;
    }
  }
  config.headers.Authorization = `Bearer ${accessToken}`;
  return api(config);
});

/** The problem-details body of a failed request, with a readable message for every case. */
export function problemOf(error) {
  if (!error?.response) {
    return { status: 0, code: 'NETWORK_ERROR', detail: NETWORK_MESSAGE, errors: [] };
  }
  const body = error.response.data ?? {};
  return {
    status: error.response.status,
    code: body.code ?? 'UNKNOWN',
    detail: body.detail ?? FALLBACK_MESSAGE,
    errors: body.errors ?? [],
  };
}
