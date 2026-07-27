import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthLayout } from '@/pages/auth/AuthLayout';
import { SignIn } from '@/pages/auth/SignIn';
import { SignUp } from '@/pages/auth/SignUp';
import { ForgotPassword } from '@/pages/auth/ForgotPassword';
import { ResetPassword } from '@/pages/auth/ResetPassword';
import { VerifyEmail } from '@/pages/auth/VerifyEmail';
import { AppShell } from '@/components/AppShell';
import { RouteErrorBoundary } from '@/components/AppErrorBoundary';
import { Landing } from '@/pages/Landing';
import { Projects } from '@/pages/Projects';
import { Canvas } from '@/pages/Canvas';
import { Workspace } from '@/pages/Workspace';
import { AdminPanel } from '@/pages/AdminPanel';
import { ModelAccess } from '@/pages/ModelAccess';
import { useAuth } from '@/hooks/useAuth';
import type { UserRole, WorkspaceMode } from '@/types';

/**
 * The legacy Upload/Transform/Dashboard/Reports surfaces now live inside the unified
 * Workspace as modes. Redirecting preserves the existing query string (notably
 * `folderId`) and sets the `mode` matching the legacy step the user came from.
 */
function RedirectToWorkspace({ mode }: { mode?: WorkspaceMode }) {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  if (mode) {
    params.set('mode', mode);
  }
  const query = params.toString();
  return <Navigate to={`/app/workspace${query ? `?${query}` : ''}`} replace />;
}

function ProtectedRoute({ children, requiredRoles }: { children: React.ReactNode; requiredRoles?: UserRole[] }) {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/signin" replace />;
  }

  if (requiredRoles && user && !requiredRoles.includes(user.role)) {
    return <Navigate to="/app/project" replace />;
  }

  return <>{children}</>;
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/app/project" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route element={<PublicRoute><AuthLayout /></PublicRoute>}>
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
      </Route>

      {/* Protected app routes */}
      <Route path="/app" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
        <Route path="canvas" element={<Canvas />} />
        <Route path="project" element={<Projects />} />
        <Route path="workspace" element={<Workspace />} />
        <Route path="upload" element={<Navigate to="/app/project" replace />} />
        <Route path="transform" element={<RedirectToWorkspace mode="prepare" />} />
        <Route path="dashboard" element={<RedirectToWorkspace mode="visualize" />} />
        <Route path="reports" element={<RedirectToWorkspace mode="publish" />} />
        <Route path="model-access" element={<ModelAccess />} />
        <Route path="admin-panel" element={<ProtectedRoute requiredRoles={['Admin']}><AdminPanel /></ProtectedRoute>} />
      </Route>

      {/* Default redirects */}
      <Route path="/" element={<Landing />} />
      <Route path="*" element={<Navigate to="/signin" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <RouteErrorBoundary>
        <AppRoutes />
      </RouteErrorBoundary>
    </BrowserRouter>
  );
}

export default App;

