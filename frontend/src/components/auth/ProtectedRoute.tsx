import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/auth.store';
import { hasPermission } from '../../lib/roleGuard';

interface ProtectedRouteProps {
  children: React.ReactNode;
  feature?: string;
  requiredPermission?: string;
}

export function ProtectedRoute({ children, requiredPermission }: ProtectedRouteProps) {
  const { jwt, role, refresh } = useAuthStore();
  const location = useLocation();
  const [checking, setChecking] = useState(!jwt);

  useEffect(() => {
    if (!jwt) {
      refresh().finally(() => setChecking(false));
    }
  }, []);

  if (checking) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-50">
        <div className="w-8 h-8 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (!jwt) {
    return <Navigate to="/auth/signin" state={{ from: location }} replace />;
  }

  if (requiredPermission && !hasPermission(role, requiredPermission)) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
