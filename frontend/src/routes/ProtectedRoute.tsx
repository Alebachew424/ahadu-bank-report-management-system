import { Navigate, Outlet } from 'react-router-dom';

export function ProtectedRoute() {
  const token = localStorage.getItem('access_token');
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

export function PermissionRoute({ permission }: { permission: string }) {
  const token = localStorage.getItem('access_token');
  const permissions = (() => {
    try {
      const stored = JSON.parse(localStorage.getItem('user_permissions') || '[]');
      return Array.isArray(stored) ? stored as string[] : [];
    } catch {
      return [];
    }
  })();
  if (!token) return <Navigate to="/login" replace />;
  if (!permissions.includes('*') && !permissions.includes(permission)) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
