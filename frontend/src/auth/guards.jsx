import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { Spinner } from '../components/ui/Spinner';
import { useAuth } from './context';

function FullPageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center text-ink-muted">
      <Spinner />
      <span className="sr-only">Loading</span>
    </div>
  );
}

function isOnboarded(user) {
  return Boolean(user.membership?.organization.onboarded_at);
}

/** Signed-out visitors go to sign-in and come back to the page they asked for. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <FullPageSpinner />;
  if (status === 'signedOut') {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

export function RequireOnboarded() {
  const { user } = useAuth();
  if (!isOnboarded(user)) return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}

export function RequireNotOnboarded() {
  const { user } = useAuth();
  if (isOnboarded(user)) {
    const org = user.membership.organization;
    const home = !org.can_hire && org.can_provide ? '/workers' : '/overview';
    return <Navigate to={home} replace />;
  }
  return <Outlet />;
}

export function RequireHirer() {
  const { user } = useAuth();
  if (!user.membership.organization.can_hire) return <Navigate to="/overview" replace />;
  return <Outlet />;
}

export function RequireProvider() {
  const { user } = useAuth();
  if (!user.membership.organization.can_provide) return <Navigate to="/overview" replace />;
  return <Outlet />;
}

export function RequireAdmin() {
  const { user } = useAuth();
  if (!user.is_platform_admin) return <Navigate to="/overview" replace />;
  return <Outlet />;
}

/** Sign-in and sign-up pages: once signed in, continue to the page that sent the user here. */
export function RedirectIfSignedIn() {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <FullPageSpinner />;
  if (status === 'signedIn') {
    const target = isOnboarded(user) ? (location.state?.from ?? '/overview') : '/onboarding';
    return <Navigate to={target} replace />;
  }
  return <Outlet />;
}
