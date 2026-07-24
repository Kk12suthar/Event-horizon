import { useCallback, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Eye, EyeOff, Loader2, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton';
import { useAuth } from '@/hooks/useAuth';
import { useToast } from '@/hooks/useToast';
import { isDevGmailSignInEnabled } from '@/lib/api';

export function SignIn() {
  const navigate = useNavigate();
  const { login, loginWithGoogle } = useAuth();
  const { error } = useToast();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const devGmailSignInEnabled = isDevGmailSignInEnabled();

  const validate = () => {
    const newErrors: { email?: string; password?: string } = {};
    if (!email) newErrors.email = 'Email is required';
    else if (!/\S+@\S+\.\S+/.test(email)) newErrors.email = 'Invalid email format';
    if (!password) newErrors.password = 'Password is required';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setIsLoading(true);
    try {
      const success = await login(email, password);
      if (success) {
        navigate('/app/project');
      }
    } catch (err) {
      error('Sign In Failed', err instanceof Error ? err.message : 'Invalid email or password');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleCredential = useCallback(async (credential: string, nonce: string) => {
    try {
      const success = await loginWithGoogle(credential, nonce);
      if (success) navigate('/app/project');
    } catch (err) {
      error('Google Sign In Failed', err instanceof Error ? err.message : 'Could not sign in with Google');
    }
  }, [error, loginWithGoogle, navigate]);

  const handleGoogleError = useCallback((message: string) => {
    error('Google Sign In', message);
  }, [error]);

  const handleDevGmailSignIn = async () => {
    const devEmail = 'tester@gmail.com';
    const devPassword = 'local-dev-password';
    setEmail(devEmail);
    setPassword(devPassword);
    setErrors({});
    setIsLoading(true);
    try {
      const success = await login(devEmail, devPassword);
      if (success) {
        navigate('/app/project');
      }
    } catch (err) {
      error('Dev Sign In Failed', err instanceof Error ? err.message : 'Could not start local Gmail session');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="animate-fade-in">
      <h1 className="text-2xl font-bold text-white">Welcome back</h1>
      <p className="mt-2 text-sm text-[#A1A1AA]">Sign in to your workspace</p>

      <div className="mt-8 space-y-4">
        <GoogleSignInButton disabled={isLoading} onCredential={handleGoogleCredential} onError={handleGoogleError} />
        <div className="flex items-center gap-3 text-xs text-[#71717A]">
          <span className="h-px flex-1 bg-[#242424]" />
          <span>or continue with email</span>
          <span className="h-px flex-1 bg-[#242424]" />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mt-5 space-y-5">
        <div>
          <Label htmlFor="email" className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">
            Email
          </Label>
          <Input
            id="email"
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setErrors(prev => ({ ...prev, email: undefined })); }}
            className={`mt-1.5 h-11 bg-[#101010] border-[#242424] text-white placeholder:text-[#71717A] focus:border-[#c16e43] focus:ring-[#c16e43]/20 ${errors.email ? 'border-[#F97066]' : ''}`}
          />
          {errors.email && <p className="mt-1 text-xs text-[#F97066]">{errors.email}</p>}
        </div>

        <div>
          <div className="flex items-center justify-between">
            <Label htmlFor="password" className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">
              Password
            </Label>
            <Link to="/forgot-password" className="text-xs text-[#E4E4E7] hover:text-[#D4D4D8] transition-colors">
              Forgot password?
            </Link>
          </div>
          <div className="relative mt-1.5">
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Enter your password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setErrors(prev => ({ ...prev, password: undefined })); }}
              className={`h-11 bg-[#101010] border-[#242424] text-white placeholder:text-[#71717A] focus:border-[#c16e43] focus:ring-[#c16e43]/20 pr-10 ${errors.password ? 'border-[#F97066]' : ''}`}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#71717A] hover:text-white transition-colors"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {errors.password && <p className="mt-1 text-xs text-[#F97066]">{errors.password}</p>}
        </div>

        <Button
          type="submit"
          disabled={isLoading}
          className="w-full h-11 bg-[#c16e43] text-[#0A0A0A] font-semibold hover:bg-[#d08a5e] transition-colors disabled:opacity-50"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Signing in...
            </>
          ) : 'Sign In'}
        </Button>

        {devGmailSignInEnabled && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-xs text-[#71717A]">
              <span className="h-px flex-1 bg-[#242424]" />
              <span>Local testing</span>
              <span className="h-px flex-1 bg-[#242424]" />
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={isLoading}
              onClick={handleDevGmailSignIn}
              className="w-full h-11 border-[#242424] bg-[#101010] text-white hover:bg-[#181818] hover:text-white"
            >
              <Mail className="w-4 h-4" />
              Continue with Gmail dev account
            </Button>
            <p className="text-xs leading-5 text-[#71717A]">
              Enabled only in local dev with VITE_ENABLE_DEV_GMAIL_SIGNIN=true. Production still uses backend Firebase auth.
            </p>
          </div>
        )}
      </form>

      <p className="mt-6 text-sm text-center text-[#A1A1AA]">
        Don't have an account?{' '}
        <Link to="/signup" className="text-[#E4E4E7] hover:text-[#D4D4D8] transition-colors font-medium">
          Sign up
        </Link>
      </p>
    </div>
  );
}
