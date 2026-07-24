import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, ArrowLeft, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/hooks/useAuth';

export function ForgotPassword() {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !/\S+@\S+\.\S+/.test(email)) {
      setError('Please enter a valid email');
      return;
    }
    setError('');
    setIsLoading(true);
    try {
      await forgotPassword(email);
      setIsLoading(false);
      setIsSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send reset email');
      setIsLoading(false);
    }
  };

  if (isSent) {
    return (
      <div className="animate-fade-in text-center">
        <div className="w-16 h-16 rounded-full bg-[#22C55E]/10 flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="w-8 h-8 text-[#22C55E]" />
        </div>
        <h1 className="text-2xl font-bold text-white">Check your email</h1>
        <p className="mt-2 text-sm text-[#A1A1AA]">
          We've sent a password reset link to <span className="text-white">{email}</span>
        </p>
        <Link to="/signin" className="inline-flex items-center gap-2 mt-6 text-sm text-[#E4E4E7] hover:text-[#D4D4D8]">
          <ArrowLeft className="w-4 h-4" />
          Back to Sign In
        </Link>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <Link to="/signin" className="inline-flex items-center gap-2 text-sm text-[#A1A1AA] hover:text-white mb-6">
        <ArrowLeft className="w-4 h-4" />
        Back to Sign In
      </Link>

      <h1 className="text-2xl font-bold text-white">Reset your password</h1>
      <p className="mt-2 text-sm text-[#A1A1AA]">
        Enter your email and we'll send you a reset link
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        <div>
          <Label htmlFor="email" className="text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Email</Label>
          <Input
            id="email"
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setError(''); }}
            className={`mt-1.5 h-11 bg-[#101010] border-[#242424] text-white placeholder:text-[#71717A] focus:border-[#c16e43] ${error ? 'border-[#F97066]' : ''}`}
          />
          {error && <p className="mt-1 text-xs text-[#F97066]">{error}</p>}
        </div>

        <Button type="submit" disabled={isLoading} className="w-full h-11 bg-[#c16e43] text-[#0A0A0A] font-semibold hover:bg-[#d08a5e] disabled:opacity-50">
          {isLoading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Sending...</> : 'Send reset link'}
        </Button>
      </form>
    </div>
  );
}
