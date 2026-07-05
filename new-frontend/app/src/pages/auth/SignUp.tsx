import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/hooks/useAuth';

export function SignUp() {
  const navigate = useNavigate();
  const { signup } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [showVerification, setShowVerification] = useState(false);

  const validate = () => {
    const newErrors: Record<string, string | undefined> = {};
    if (!name.trim()) newErrors.name = 'Name is required';
    if (!email) newErrors.email = 'Email is required';
    else if (!/\S+@\S+\.\S+/.test(email)) newErrors.email = 'Invalid email format';
    if (!password) newErrors.password = 'Password is required';
    else if (password.length < 6) newErrors.password = 'Password must be at least 6 characters';
    if (password !== confirmPassword) newErrors.confirmPassword = 'Passwords do not match';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    setIsLoading(true);
    try {
      await signup(name, email, password);
      setShowVerification(true);
    } catch {
      // handled
    } finally {
      setIsLoading(false);
    }
  };

  if (showVerification) {
    return (
      <div className="animate-fade-in text-center">
        <div className="w-16 h-16 rounded-full bg-[#22C55E]/10 flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-[#22C55E]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-white">Verify your email</h1>
        <p className="mt-2 text-sm text-[#A1A1AA]">
          We've sent a verification link to <span className="text-white">{email}</span>
        </p>
        <Button
          onClick={() => navigate('/signin')}
          className="mt-6 h-11 bg-[#c16e43] text-[#0A0A0A] font-semibold hover:bg-[#d08a5e]"
        >
          Go to Sign In
        </Button>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-2xl font-bold text-white">Create your account</h1>
      <p className="mt-2 text-sm text-[#A1A1AA]">Start your data intelligence journey</p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        <div>
          <Label htmlFor="name" className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Full Name</Label>
          <Input
            id="name"
            type="text"
            placeholder="Your full name"
            value={name}
            onChange={(e) => { setName(e.target.value); setErrors(p => ({ ...p, name: undefined })); }}
            className={`mt-1.5 h-11 bg-[#161616] border-[#2A2A2A] text-white placeholder:text-[#71717A] focus:border-[#c16e43] ${errors.name ? 'border-[#F97066]' : ''}`}
          />
          {errors.name && <p className="mt-1 text-xs text-[#F97066]">{errors.name}</p>}
        </div>

        <div>
          <Label htmlFor="email" className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Email</Label>
          <Input
            id="email"
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setErrors(p => ({ ...p, email: undefined })); }}
            className={`mt-1.5 h-11 bg-[#161616] border-[#2A2A2A] text-white placeholder:text-[#71717A] focus:border-[#c16e43] ${errors.email ? 'border-[#F97066]' : ''}`}
          />
          {errors.email && <p className="mt-1 text-xs text-[#F97066]">{errors.email}</p>}
        </div>

        <div>
          <Label htmlFor="password" className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Password</Label>
          <div className="relative mt-1.5">
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Create a password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setErrors(p => ({ ...p, password: undefined })); }}
              className={`h-11 bg-[#161616] border-[#2A2A2A] text-white placeholder:text-[#71717A] focus:border-[#c16e43] pr-10 ${errors.password ? 'border-[#F97066]' : ''}`}
            />
            <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#71717A] hover:text-white">
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {errors.password && <p className="mt-1 text-xs text-[#F97066]">{errors.password}</p>}
        </div>

        <div>
          <Label htmlFor="confirm" className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Confirm Password</Label>
          <div className="relative mt-1.5">
            <Input
              id="confirm"
              type={showConfirm ? 'text' : 'password'}
              placeholder="Confirm your password"
              value={confirmPassword}
              onChange={(e) => { setConfirmPassword(e.target.value); setErrors(p => ({ ...p, confirmPassword: undefined })); }}
              className={`h-11 bg-[#161616] border-[#2A2A2A] text-white placeholder:text-[#71717A] focus:border-[#c16e43] pr-10 ${errors.confirmPassword ? 'border-[#F97066]' : ''}`}
            />
            <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#71717A] hover:text-white">
              {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {errors.confirmPassword && <p className="mt-1 text-xs text-[#F97066]">{errors.confirmPassword}</p>}
        </div>

        <Button type="submit" disabled={isLoading} className="w-full h-11 bg-[#c16e43] text-[#0A0A0A] font-semibold hover:bg-[#d08a5e] disabled:opacity-50">
          {isLoading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Creating account...</> : 'Create Account'}
        </Button>
      </form>

      <p className="mt-6 text-sm text-center text-[#A1A1AA]">
        Already have an account?{' '}
        <Link to="/signin" className="text-[#E4E4E7] hover:text-[#D4D4D8] font-medium">Sign in</Link>
      </p>
    </div>
  );
}
