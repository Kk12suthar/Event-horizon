import { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';

export function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('oobCode') || searchParams.get('token');
  const { verifyEmail } = useAuth();
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying');
  const [countdown, setCountdown] = useState(3);

  useEffect(() => {
    let cancelled = false;
    const runVerification = async () => {
      if (token) {
        try {
          await verifyEmail(token);
          if (!cancelled) setStatus('success');
        } catch {
          if (!cancelled) setStatus('error');
        }
      } else {
        if (!cancelled) setStatus('error');
      }
    };
    void runVerification();
    return () => {
      cancelled = true;
    };
  }, [token, verifyEmail]);

  useEffect(() => {
    if (status === 'success' && countdown > 0) {
      const timer = setTimeout(() => setCountdown(c => c - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [status, countdown]);

  if (status === 'verifying') {
    return (
      <div className="animate-fade-in text-center">
        <Loader2 className="w-10 h-10 text-[#E4E4E7] animate-spin mx-auto mb-4" />
        <h1 className="text-2xl font-bold text-white">Verifying your email</h1>
        <p className="mt-2 text-sm text-[#A1A1AA]">Please wait while we verify your email address...</p>
      </div>
    );
  }

  if (status === 'success') {
    return (
      <div className="animate-fade-in text-center">
        <div className="w-16 h-16 rounded-full bg-[#22C55E]/10 flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="w-8 h-8 text-[#22C55E]" />
        </div>
        <h1 className="text-2xl font-bold text-white">Email verified!</h1>
        <p className="mt-2 text-sm text-[#A1A1AA]">
          Redirecting to sign in in {countdown} seconds...
        </p>
        <Link to="/signin">
          <Button className="mt-6 h-11 bg-[#c16e43] text-[#0A0A0A] font-semibold hover:bg-[#d08a5e]">
            Sign In Now
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="animate-fade-in text-center">
      <div className="w-16 h-16 rounded-full bg-[#F97066]/10 flex items-center justify-center mx-auto mb-4">
        <XCircle className="w-8 h-8 text-[#F97066]" />
      </div>
      <h1 className="text-2xl font-bold text-white">Verification failed</h1>
      <p className="mt-2 text-sm text-[#A1A1AA]">The verification link is invalid or expired.</p>
      <div className="flex justify-center gap-3 mt-6">
        <Link to="/signup">
          <Button variant="outline" className="h-11 border-[#242424] text-[#A1A1AA] hover:bg-[#1C1C1C]">
            Back to Sign Up
          </Button>
        </Link>
        <Link to="/signin">
          <Button className="h-11 bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">
            Sign In
          </Button>
        </Link>
      </div>
    </div>
  );
}
