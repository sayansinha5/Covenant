import { AxiosError } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, problemOf, refreshSession, setAccessToken, setSessionHandlers } from './api';

function respond(config, status, data) {
  const response = { status, data, headers: {}, config, statusText: String(status) };
  if (status >= 400) {
    throw new AxiosError(`HTTP ${status}`, 'ERR_BAD_REQUEST', config, null, response);
  }
  return response;
}

describe('api client', () => {
  let calls;
  let validToken;
  let refreshOk;

  beforeEach(() => {
    calls = [];
    validToken = 'new-token';
    refreshOk = true;
    setAccessToken('old-token');
    api.defaults.adapter = async (config) => {
      calls.push({ url: config.url, auth: config.headers.Authorization, headers: config.headers });
      if (config.url === '/auth/refresh') {
        await new Promise((resolve) => setTimeout(resolve, 5));
        return refreshOk
          ? respond(config, 200, { access_token: validToken, user: { id: 'u1' } })
          : respond(config, 401, { code: 'INVALID_REFRESH_TOKEN' });
      }
      return config.headers.Authorization === `Bearer ${validToken}`
        ? respond(config, 200, { ok: true })
        : respond(config, 401, { code: 'NOT_AUTHENTICATED' });
    };
  });

  afterEach(() => {
    setSessionHandlers({ onRefreshed: () => {}, onExpired: () => {} });
  });

  it('refreshes once for concurrent 401s and retries each request', async () => {
    const results = await Promise.all([api.get('/a'), api.get('/b'), api.get('/c')]);
    expect(results.map((r) => r.data.ok)).toEqual([true, true, true]);
    expect(calls.filter((c) => c.url === '/auth/refresh')).toHaveLength(1);
  });

  it('shares one refresh between direct callers', async () => {
    const [first, second] = await Promise.all([refreshSession(), refreshSession()]);
    expect(first).toBe(second);
    expect(calls).toHaveLength(1);
  });

  it('sends the CSRF header on refresh and a request id on every call', async () => {
    await api.get('/a');
    const refresh = calls.find((c) => c.url === '/auth/refresh');
    expect(refresh.headers['X-Requested-With']).toBe('covenant');
    expect(calls.every((c) => /^[0-9a-f-]{36}$/.test(c.headers['X-Request-ID']))).toBe(true);
  });

  it('reports an expired session when the refresh fails', async () => {
    refreshOk = false;
    const onExpired = vi.fn();
    setSessionHandlers({ onExpired });
    await expect(api.get('/a')).rejects.toMatchObject({ response: { status: 401 } });
    expect(onExpired).toHaveBeenCalledOnce();
  });

  it('turns failures into readable problems', () => {
    expect(problemOf(new AxiosError('offline')).code).toBe('NETWORK_ERROR');
    const error = new AxiosError('x', 'ERR', {}, null, {
      status: 409,
      data: { code: 'EMAIL_TAKEN', detail: 'An account with this email already exists.' },
    });
    expect(problemOf(error)).toMatchObject({ status: 409, code: 'EMAIL_TAKEN', errors: [] });
  });
});
