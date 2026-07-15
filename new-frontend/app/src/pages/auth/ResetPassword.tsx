import { useState } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/hooks/useAuth';

export function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { resetPassword } = useAuth();
  const token = searchParams.get('oobCode') || searchParams.get('token');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});

  if (!token) {
    return (
      <div className="animate-fade-in">
        <div className="p-4 rounded-lg bg-[#F97066]/10 border border-[#F97066]/20 mb-6">
          <p className="text-sm text-[#F97066]">
            This reset link is invalid or expired.
          </p>
        </div>
        <Link to="/signin" className="inline-flex items-center gap-2 text-sm text-[#E4E4E7] hover:text-[#D4D4D8]">
          <ArrowLeft className="w-4 h-4" />
          Back to Sign In
        </Link>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string | undefined> = {};
    if (!password) newErrors.password = 'Password is required';
    else if (password.length < 6) newErrors.password = 'At least 6 characters';
    if (password !== confirm) newErrors.confirm = 'Passwords do not match';
    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) return;

    setIsLoading(true);
    try {
      await resetPassword(token, password);
      setIsLoading(false);
      setIsSuccess(true);
    } catch (error) {
      setErrors({ password: error instanceof Error ? error.message : 'Failed to update password' });
      setIsLoading(false);
    }
  };

  if (isSuccess) {
    return (
      <div className="animate-fade-in text-center">
        <div className="w-16 h-16 rounded-full bg-[#22C55E]/10 flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-[#22C55E]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-white">Password updated</h1>
        <p className="mt-2 text-sm text-[#A1A1AA]">Your password has been successfully reset.</p>
        <Button onClick={() => navigate('/signin')} className="mt-6 h-11 bg-[#c16e43] text-[#0A0A0A] font-semibold hover:bg-[#d08a5e]">
          Sign In Now
        </Button>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <Link to="/signin" className="inline-flex items-center gap-2 text-sm text-[#A1A1AA] hover:text-white mb-6">
        <ArrowLeft className="w-4 h-4" />
        Back to Sign In
      </Link>

      <h1 className="text-2xl font-bold text-white">Set new password</h1>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        <div>
          <Label className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">New Password</Label>
          <div className="relative mt-1.5">
            <Input
              type={showPassword ? 'text' : 'password'}
              placeholder="Enter new password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setErrors(p => ({ ...p, password: undefined })); }}
              className={`h-11 bg-[#101010] border-[#242424] text-white placeholder:text-[#71717A] focus:border-[#c16e43] pr-10 ${errors.password ? 'border-[#F97066]' : ''}`}
            />
            <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#71717A] hover:text-white">
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {errors.password && <p className="mt-1 text-xs text-[#F97066]">{errors.password}</p>}
        </div>

        <div>
          <Label className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Confirm New Password</Label>
          <div className="relative mt-1.5">
            <Input
              type={showConfirm ? 'text' : 'password'}
              placeholder="Confirm new password"
              value={confirm}
              onChange={(e) => { setConfirm(e.target.value); setErrors(p => ({ ...p, confirm: undefined })); }}
              className={`h-11 bg-[#101010] border-[#242424] text-white placeholder:text-[#71717A] focus:border-[#c16e43] pr-10 ${errors.confirm ? 'border-[#F97066]' : ''}`}
            />
            <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#71717A] hover:text-white">
              {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {errors.confirm && <p className="mt-1 text-xs text-[#F97066]">{errors.confirm}</p>}
        </div>

        <Button type="submit" disabled={isLoading} className="w-full h-11 bg-[#c16e43] text-[#0A0A0A] font-semibold hover:bg-[#d08a5e] disabled:opacity-50">
          {isLoading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Updating...</> : 'Update Password'}
        </Button>
      </form>
    </div>
  );
}
