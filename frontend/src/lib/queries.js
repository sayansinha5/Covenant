import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { isRunActive } from './admin';
import { api } from './api';

export const FUNDING_ACCOUNT_KEY = ['paypal', 'funding-account'];
export const MANDATE_KEY = ['mandate'];
export const MANDATE_VERSIONS_KEY = ['mandate', 'versions'];
export const ADMIN_WORKERS_KEY = ['admin', 'workers'];
export const WEBHOOK_EVENTS_KEY = ['admin', 'webhook-events'];
export const LAST_RECONCILIATION_KEY = ['admin', 'reconcile', 'last'];

const PAGE_SIZE = 25;
const RECONCILE_POLL_MS = 2000;

function usePage(key, path, page) {
  return useQuery({
    queryKey: [...key, page],
    queryFn: async () => (await api.get(path, { params: { page, page_size: PAGE_SIZE } })).data,
    placeholderData: keepPreviousData,
  });
}

export function useAdminWorkers(page) {
  return usePage(ADMIN_WORKERS_KEY, '/admin/workers', page);
}

export function useWebhookEvents(page) {
  return usePage(WEBHOOK_EVENTS_KEY, '/admin/webhook-events', page);
}

export const MY_WORKERS_KEY = ['workers', 'mine'];

export function useMyWorkers() {
  return useQuery({
    queryKey: MY_WORKERS_KEY,
    queryFn: async () => (await api.get('/workers/mine')).data,
  });
}

export function useMarketplace(filters) {
  return useQuery({
    queryKey: ['workers', 'marketplace', filters],
    queryFn: async () => (await api.get('/workers', { params: filters })).data,
    placeholderData: keepPreviousData,
  });
}

export function useWorker(workerId) {
  return useQuery({
    queryKey: ['workers', workerId],
    queryFn: async () => (await api.get(`/workers/${workerId}`)).data,
    enabled: Boolean(workerId),
  });
}

export function useVerification(workerId, active) {
  return useQuery({
    queryKey: ['workers', workerId, 'verification'],
    queryFn: async () => (await api.get(`/workers/${workerId}/verification`)).data,
    enabled: Boolean(workerId),
    refetchInterval: (query) => {
      if (!active) return false;
      const status = query.state.data?.status;
      return status && status !== 'pending' ? false : 2000;
    },
  });
}

export function useLastReconciliation() {
  return useQuery({
    queryKey: LAST_RECONCILIATION_KEY,
    queryFn: async () => (await api.get('/admin/reconcile/last')).data,
    refetchInterval: (query) => (isRunActive(query.state.data) ? RECONCILE_POLL_MS : false),
  });
}

export function useFundingAccount() {
  return useQuery({
    queryKey: FUNDING_ACCOUNT_KEY,
    queryFn: async () => (await api.get('/paypal/funding-account')).data,
  });
}

export function useMandate() {
  return useQuery({
    queryKey: MANDATE_KEY,
    queryFn: async () => (await api.get('/mandate')).data,
  });
}

export function useMandateVersions() {
  return useQuery({
    queryKey: MANDATE_VERSIONS_KEY,
    queryFn: async () => (await api.get('/mandate/versions')).data,
  });
}

export const CONTRACTS_KEY = ['contracts'];
export const CONTRACT_KEY = ['contract'];
export const OVERVIEW_KEY = ['overview'];
export const NOTIFICATIONS_KEY = ['notifications'];
export const APPROVALS_KEY = ['approvals'];
export const LEDGER_KEY = ['ledger'];
export const EARNINGS_KEY = ['earnings'];
export const API_KEYS_KEY = ['api-keys'];

const POLL_MS = Number(import.meta.env.VITE_CONTRACT_POLL_MS) || 2000;

export function useOverview() {
  return useQuery({
    queryKey: OVERVIEW_KEY,
    queryFn: async () => (await api.get('/overview')).data,
  });
}

export function useContracts(role) {
  return useQuery({
    queryKey: [...CONTRACTS_KEY, role ?? 'all'],
    queryFn: async () => (await api.get('/contracts', { params: { role, page_size: 100 } })).data,
  });
}

export function useContract(id) {
  return useQuery({
    queryKey: [...CONTRACT_KEY, id],
    enabled: Boolean(id),
    queryFn: async () => (await api.get(`/contracts/${id}`)).data,
    refetchInterval: POLL_MS,
  });
}

export function useApprovals({ enabled = true } = {}) {
  return useQuery({
    queryKey: APPROVALS_KEY,
    queryFn: async () => (await api.get('/approvals')).data,
    enabled,
  });
}

export function useLedger() {
  return useQuery({
    queryKey: LEDGER_KEY,
    queryFn: async () => (await api.get('/ledger', { params: { page_size: 500 } })).data,
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: async () => (await api.get('/notifications')).data,
    refetchInterval: 15000,
  });
}

export function useEarnings() {
  return useQuery({
    queryKey: EARNINGS_KEY,
    queryFn: async () => (await api.get('/earnings/summary')).data,
  });
}

export function useSchedule() {
  return useQuery({
    queryKey: ['schedule'],
    queryFn: async () => (await api.get('/schedule')).data,
  });
}

export function useFleet() {
  return useQuery({
    queryKey: ['fleet'],
    queryFn: async () => (await api.get('/fleet')).data,
  });
}

export function useApiKeys() {
  return useQuery({
    queryKey: API_KEYS_KEY,
    queryFn: async () => (await api.get('/api-keys')).data,
  });
}
