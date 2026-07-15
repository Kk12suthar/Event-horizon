import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { User, UserRole } from '@/types';
import {
  clearStoredAuth,
  forgotPasswordRequest,
  googleSignInRequest,
  isDevGmailSignInEnabled,
  logoutRequest,
  normalizeRole,
  resetPasswordRequest,
  signInRequest,
  signUpRequest,
  verifyEmailRequest,
} from '@/lib/api';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<boolean>;
  loginWithGoogle: (credential: string, nonce: string) => Promise<boolean>;
  signup: (name: string, email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  forgotPassword: (email: string) => Promise<boolean>;
  resetPassword: (oobCode: string, newPassword: string) => Promise<boolean>;
  verifyEmail: (oobCode: string) => Promise<boolean>;
  hasRole: (roles: UserRole[]) => boolean;
  isAdmin: boolean;
  isAnalyst: boolean;
  isViewer: boolean;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const toUser = (backendUser: Record<string, unknown>, firebaseUid?: string, firebaseEmail?: string): User => {
  const role = normalizeRole(backendUser.role);
  const firstName = String(backendUser.name || backendUser.full_name || backendUser.username || '').trim();
  const email = String(firebaseEmail || backendUser.email || '');
  return {
    id: String(backendUser.id || backendUser.user_id || firebaseUid || ''),
    uid: firebaseUid || String(backendUser.uid || ''),
    name: firstName || email || 'User',
    email,
    role,
    status: String(backendUser.status || 'active').toLowerCase() === 'inactive' ? 'inactive' : 'active',
    createdAt: String(backendUser.created_at || backendUser.createdAt || ''),
    raw: backendUser,
  };
};

const loadStoredUser = (): User | null => {
  const stored = sessionStorage.getItem('user');
  const accessToken = sessionStorage.getItem('access_token');
  if (!stored || !accessToken) return null;

  // A frontend-only Gmail dev token (e.g. from an older build, or a session
  // started while the backend was unreachable) is never a valid JWT and the
  // backend will reject every request with it. Don't restore that as an
  // authenticated session on reload; force the user back to sign-in instead.
  const isStaleFrontendOnlyDevToken =
    !isDevGmailSignInEnabled() && accessToken.startsWith('dev-gmail-access-');
  if (isStaleFrontendOnlyDevToken) {
    clearStoredAuth();
    return null;
  }

  try {
    const parsed = JSON.parse(stored) as User;
    return {
      ...parsed,
      role: normalizeRole(parsed.role),
      status: parsed.status === 'inactive' ? 'inactive' : 'active',
    };
  } catch {
    clearStoredAuth();
    return null;
  }
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => loadStoredUser());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) return undefined;

    const timeoutMs = Number(sessionStorage.getItem('inactivity_timeout_ms') || 30 * 60 * 1000);
    if (!sessionStorage.getItem('last_activity')) {
      sessionStorage.setItem('last_activity', String(Date.now()));
    }

    let activityTimer: number | undefined;
    const markActivity = () => {
      if (activityTimer) return;
      activityTimer = window.setTimeout(() => {
        sessionStorage.setItem('last_activity', String(Date.now()));
        activityTimer = undefined;
      }, 1000);
    };

    const events = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'click'];
    events.forEach((event) => document.addEventListener(event, markActivity, { passive: true }));

    const interval = window.setInterval(() => {
      const lastActivity = Number(sessionStorage.getItem('last_activity') || 0);
      if (lastActivity > 0 && Date.now() - lastActivity > timeoutMs) {
        clearStoredAuth();
        setUser(null);
      }
    }, 30_000);

    return () => {
      events.forEach((event) => document.removeEventListener(event, markActivity));
      window.clearInterval(interval);
      if (activityTimer) window.clearTimeout(activityTimer);
    };
  }, [user]);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    try {
      const session = await signInRequest(email, password);
      const mappedUser = toUser(session.backendUser, session.firebaseUid, session.firebaseEmail);

      sessionStorage.setItem('access_token', session.accessToken);
      sessionStorage.setItem('refresh_token', session.refreshToken);
      sessionStorage.setItem('token_expiry', String(Date.now() + session.expiresIn * 1000));
      sessionStorage.setItem('inactivity_timeout_ms', String(session.expiresIn * 1000));
      sessionStorage.setItem('last_activity', String(Date.now()));
      sessionStorage.setItem('user', JSON.stringify(mappedUser));
      sessionStorage.setItem('userId', mappedUser.id);
      if (mappedUser.uid) sessionStorage.setItem('firebaseUid', mappedUser.uid);

      setUser(mappedUser);
      return true;
    } finally {
      setLoading(false);
    }
  }, []);

  const loginWithGoogle = useCallback(async (credential: string, nonce: string) => {
    setLoading(true);
    try {
      const session = await googleSignInRequest(credential, nonce);
      const mappedUser = toUser(session.backendUser, session.firebaseUid, session.firebaseEmail);
      sessionStorage.setItem('access_token', session.accessToken);
      sessionStorage.setItem('refresh_token', session.refreshToken);
      sessionStorage.setItem('token_expiry', String(Date.now() + session.expiresIn * 1000));
      sessionStorage.setItem('inactivity_timeout_ms', String(session.expiresIn * 1000));
      sessionStorage.setItem('last_activity', String(Date.now()));
      sessionStorage.setItem('user', JSON.stringify(mappedUser));
      sessionStorage.setItem('userId', mappedUser.id);
      if (mappedUser.uid) sessionStorage.setItem('firebaseUid', mappedUser.uid);
      setUser(mappedUser);
      return true;
    } finally {
      setLoading(false);
    }
  }, []);

  const signup = useCallback(async (name: string, email: string, password: string) => {
    setLoading(true);
    try {
      await signUpRequest(name, email, password);
      return true;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    clearStoredAuth();
    setUser(null);
  }, []);

  const forgotPassword = useCallback(async (email: string) => {
    await forgotPasswordRequest(email);
    return true;
  }, []);

  const resetPassword = useCallback(async (oobCode: string, newPassword: string) => {
    await resetPasswordRequest(oobCode, newPassword);
    return true;
  }, []);

  const verifyEmail = useCallback(async (oobCode: string) => {
    await verifyEmailRequest(oobCode);
    return true;
  }, []);

  const hasRole = useCallback((roles: UserRole[]) => !!user && roles.includes(user.role), [user]);

  const value = useMemo<AuthContextValue>(() => {
    const isAdmin = user?.role === 'Admin';
    const isAnalyst = user?.role === 'Analyst' || isAdmin;
    return {
      user,
      loading,
      login,
      loginWithGoogle,
      signup,
      logout,
      forgotPassword,
      resetPassword,
      verifyEmail,
      hasRole,
      isAdmin,
      isAnalyst,
      isViewer: user?.role === 'Viewer',
      isAuthenticated: !!user && !!sessionStorage.getItem('access_token'),
    };
  }, [forgotPassword, hasRole, loading, login, loginWithGoogle, logout, resetPassword, signup, user, verifyEmail]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
