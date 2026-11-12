import { useEffect, useEffectEvent, useRef, useState } from 'react';

import { api, problemOf } from './api';

const API_ORIGIN = new URL(import.meta.env.VITE_API_BASE_URL).origin;
const POLL_MS = 2000;
const POPUP_FEATURES = 'popup,width=480,height=720';

const CANCELLED = 'PayPal connection was cancelled. Nothing was saved.';
const WINDOW_CLOSED =
  'The PayPal window was closed before the connection finished. Nothing was saved.';

/**
 * The "Connect PayPal" flow (W2). PayPal runs in a popup; the backend's return page posts a
 * message back, and the session is also polled in case the message is lost. Closing the popup
 * cancels the session. A blocked popup falls back to a full-page redirect.
 *
 * status: idle | starting | waiting | blocked | cancelled | failed | connected
 */
export function usePayPalConnect({ returnPath, onConnected }) {
  const [state, setState] = useState({ status: 'idle', message: null });
  const sessionId = useRef(null);
  const popupRef = useRef(null);

  function settle(status, reason) {
    sessionId.current = null;
    popupRef.current = null;
    if (status === 'connected') {
      setState({ status: 'connected', message: null });
      onConnected?.();
    } else if (status === 'cancelled') {
      setState({ status: 'cancelled', message: reason ?? CANCELLED });
    } else {
      setState({
        status: 'failed',
        message: `${reason ?? "PayPal connection didn't complete."} Nothing was saved.`,
      });
    }
  }
  const finish = useEffectEvent(settle);

  async function closedWithoutFinishing(id) {
    if (sessionId.current !== id) return;
    settle('cancelled', WINDOW_CLOSED);
    await api.post(`/paypal/vault/sessions/${id}/cancel`).catch(() => {});
  }
  const abandon = useEffectEvent(closedWithoutFinishing);

  useEffect(() => {
    function onMessage(event) {
      const data = event.data;
      if (event.origin !== API_ORIGIN || data?.source !== 'covenant') return;
      if (data.type === 'paypal-vault' && data.sessionId === sessionId.current) finish(data.status);
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  useEffect(() => {
    if (state.status !== 'waiting') return undefined;
    const timer = setInterval(async () => {
      const id = sessionId.current;
      if (!id) return;
      // Read before polling: the return page closes the popup only after the session settles.
      const closed = popupRef.current?.closed ?? false;
      try {
        const { data } = await api.get(`/paypal/vault/sessions/${id}`);
        if (data.status !== 'pending') finish(data.status, data.failure_reason);
        else if (closed) abandon(id);
      } catch {
        // A transient poll failure is retried on the next tick.
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [state.status]);

  async function start() {
    const { data } = await api.post('/paypal/vault/start', { return_path: returnPath });
    sessionId.current = data.session_id;
    return data.approve_url;
  }

  async function connect() {
    // Opened synchronously inside the click, or the browser treats it as an unwanted popup.
    const popup = window.open('', 'covenant-paypal', POPUP_FEATURES);
    if (!popup) {
      setState({ status: 'blocked', message: null });
      return;
    }
    popup.document.title = 'Connecting to PayPal…';
    popup.document.body.textContent = 'Opening PayPal…';
    setState({ status: 'starting', message: null });
    try {
      popup.location.href = await start();
      popupRef.current = popup;
      setState({ status: 'waiting', message: null });
    } catch (error) {
      popup.close();
      setState({ status: 'failed', message: problemOf(error).detail });
    }
  }

  async function continueInThisTab() {
    setState({ status: 'starting', message: null });
    try {
      window.location.assign(await start());
    } catch (error) {
      setState({ status: 'failed', message: problemOf(error).detail });
    }
  }

  async function cancel() {
    const id = sessionId.current;
    popupRef.current?.close();
    settle('cancelled');
    if (id) await api.post(`/paypal/vault/sessions/${id}/cancel`).catch(() => {});
  }

  /** After a full-page redirect the outcome arrives as ?paypal=… on the return path. */
  function showRedirectOutcome(outcome) {
    if (outcome === 'cancelled' || outcome === 'failed') settle(outcome);
    else if (outcome === 'invalid') settle('failed', 'This PayPal link is no longer valid.');
  }

  return { ...state, connect, continueInThisTab, cancel, showRedirectOutcome };
}
