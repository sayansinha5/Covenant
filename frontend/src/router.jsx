import { createBrowserRouter, Navigate, useLocation } from 'react-router-dom';

import {
  RedirectIfSignedIn,
  RequireAdmin,
  RequireAuth,
  RequireHirer,
  RequireNotOnboarded,
  RequireProvider,
  RequireOnboarded,
} from './auth/guards';
import { AppLayout } from './components/layout/AppLayout';
import { Admin } from './pages/admin/Admin';
import { Approvals } from './pages/Approvals';
import { Assistant } from './pages/Assistant';
import { SignIn } from './pages/auth/SignIn';
import { SignUp } from './pages/auth/SignUp';
import { ContractDetail } from './pages/ContractDetail';
import { Catalog } from './pages/Catalog';
import { Contracts } from './pages/Contracts';
import { Earnings } from './pages/Earnings';
import { Fleet } from './pages/Fleet';
import { Jobs } from './pages/Jobs';
import { Ledger } from './pages/Ledger';
import { Mandate } from './pages/Mandate';
import { About } from './pages/About';
import { Careers } from './pages/Careers';
import { Guides } from './pages/Guides';
import { Landing } from './pages/Landing';
import { Privacy } from './pages/Privacy';
import { Terms } from './pages/Terms';
import { Marketplace } from './pages/Marketplace';
import { MyWorkers } from './pages/MyWorkers';
import { NotFound } from './pages/NotFound';
import { Onboarding } from './pages/onboarding/Onboarding';
import { Overview } from './pages/Overview';
import { ScheduleRoute } from './pages/ScheduleRoute';
import { Settings } from './pages/Settings';

function FindWorkersRedirect() {
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: '/find-workers', search, hash }} replace />;
}

export const router = createBrowserRouter([
  { path: '/', element: <Landing /> },
  { path: '/about', element: <About /> },
  { path: '/guides', element: <Guides /> },
  { path: '/careers', element: <Careers /> },
  { path: '/privacy', element: <Privacy /> },
  { path: '/terms', element: <Terms /> },
  {
    element: <RedirectIfSignedIn />,
    children: [
      { path: '/login', element: <SignIn /> },
      { path: '/register', element: <SignUp /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <RequireNotOnboarded />,
        children: [{ path: '/onboarding', element: <Onboarding /> }],
      },
      {
        element: <RequireOnboarded />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { path: '/overview', element: <Overview />, handle: { title: 'Overview' } },
              { path: '/contracts', element: <Contracts />, handle: { title: 'Contracts' } },
              {
                path: '/contracts/:contractId',
                element: <ContractDetail />,
                handle: { title: 'Contract' },
              },
              { path: '/ledger', element: <Ledger />, handle: { title: 'Ledger' } },
              {
                path: '/schedule',
                element: <ScheduleRoute />,
                handle: { title: 'Schedule' },
              },
              { path: '/fleet', element: <Fleet />, handle: { title: 'Fleet' } },
              { path: '/settings', element: <Settings />, handle: { title: 'Settings' } },
              {
                element: <RequireHirer />,
                children: [
                  {
                    path: '/assistant',
                    element: <Assistant />,
                    handle: { title: 'Assistant', bleed: true },
                  },
                  { path: '/approvals', element: <Approvals />, handle: { title: 'Approvals' } },
                  { path: '/mandate', element: <Mandate />, handle: { title: 'Mandate' } },
                  {
                    path: '/find-workers',
                    element: <Marketplace />,
                    handle: { title: 'Find Workers' },
                  },
                  { path: '/marketplace', element: <FindWorkersRedirect /> },
                  { path: '/catalog', element: <Catalog />, handle: { title: 'Catalog' } },
                ],
              },
              {
                element: <RequireProvider />,
                children: [
                  { path: '/workers', element: <MyWorkers />, handle: { title: 'My workers' } },
                  { path: '/jobs', element: <Jobs />, handle: { title: 'Jobs' } },
                  { path: '/earnings', element: <Earnings />, handle: { title: 'Earnings' } },
                ],
              },
              {
                element: <RequireAdmin />,
                children: [{ path: '/admin', element: <Admin />, handle: { title: 'Admin' } }],
              },
              { path: '*', element: <NotFound />, handle: { title: 'Not found' } },
            ],
          },
        ],
      },
    ],
  },
]);
