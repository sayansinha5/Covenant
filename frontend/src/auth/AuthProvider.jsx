import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { api, endSession, refreshSession, setAccessToken, setSessionHandlers } from '../lib/api';
import { AuthContext } from './context';

const SIGNED_OUT = { status: 'signedOut', user: null };

/** The access token lives only in memory; on load the session is restored from the refresh cookie. */
export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState({ status: 'loading', user: null });

  useEffect(() => {
    setSessionHandlers({
      onRefreshed: (session) => setState({ status: 'signedIn', user: session.user }),
      onExpired: () => {
        queryClient.clear();
        setState(SIGNED_OUT);
      },
    });
    refreshSession().catch(() => setState(SIGNED_OUT));
  }, [queryClient]);

  const startSession = useCallback((session) => {
    setAccessToken(session.access_token);
    setState({ status: 'signedIn', user: session.user });
  }, []);

  const reloadUser = useCallback(async () => {
    const { data } = await api.get('/auth/me');
    setState({ status: 'signedIn', user: data });
    return data;
  }, []);

  /** After creating an organization the server issues a token carrying the new org and role. */
  const switchAccessToken = useCallback(
    async (token) => {
      setAccessToken(token);
      return reloadUser();
    },
    [reloadUser],
  );

  const signOut = useCallback(async () => {
    try {
      await endSession();
    } finally {
      queryClient.clear();
      setState(SIGNED_OUT);
    }
  }, [queryClient]);

  const value = useMemo(
    () => ({ ...state, startSession, reloadUser, switchAccessToken, signOut }),
    [state, startSession, reloadUser, switchAccessToken, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
