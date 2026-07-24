import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { getGoogleSignInConfig } from '@/lib/api';

interface GoogleCredentialResponse {
  credential?: string;
}

interface GoogleAccountsId {
  initialize: (options: Record<string, unknown>) => void;
  renderButton: (element: HTMLElement, options: Record<string, unknown>) => void;
  cancel: () => void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } };
  }
}

interface GoogleSignInButtonProps {
  disabled?: boolean;
  onCredential: (credential: string, nonce: string) => Promise<void>;
  onAvailabilityChange?: (enabled: boolean) => void;
  onError: (message: string) => void;
}

const SCRIPT_ID = 'google-identity-services';

const createNonce = () => {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
};

const loadGoogleScript = () => new Promise<void>((resolve, reject) => {
  if (window.google?.accounts?.id) {
    resolve();
    return;
  }
  const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
  if (existing) {
    existing.addEventListener('load', () => resolve(), { once: true });
    existing.addEventListener('error', () => reject(new Error('Google sign-in failed to load.')), { once: true });
    return;
  }
  const script = document.createElement('script');
  script.id = SCRIPT_ID;
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  script.defer = true;
  script.onload = () => resolve();
  script.onerror = () => reject(new Error('Google sign-in failed to load.'));
  document.head.appendChild(script);
});

export function GoogleSignInButton({ disabled, onCredential, onError, onAvailabilityChange }: GoogleSignInButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let active = true;
    const nonce = createNonce();
    void getGoogleSignInConfig()
      .then(async (config) => {
        if (!active) return;
        if (!config.enabled || !config.client_id) {
          setUnavailable(true);
          onAvailabilityChange?.(false);
          return;
        }
        await loadGoogleScript();
        if (!active || !containerRef.current || !window.google) return;
        setEnabled(true);
        onAvailabilityChange?.(true);
        window.google.accounts.id.initialize({
          client_id: config.client_id,
          nonce,
          auto_select: false,
          cancel_on_tap_outside: true,
          use_fedcm_for_prompt: true,
          callback: (response: GoogleCredentialResponse) => {
            if (!response.credential) {
              onError('Google did not return a sign-in credential.');
              return;
            }
            setWorking(true);
            void onCredential(response.credential, nonce).finally(() => setWorking(false));
          },
        });
        containerRef.current.replaceChildren();
        window.google.accounts.id.renderButton(containerRef.current, {
          type: 'standard',
          theme: 'filled_black',
          size: 'large',
          shape: 'rectangular',
          text: 'continue_with',
          width: Math.max(220, Math.floor(containerRef.current.clientWidth)),
        });
      })
      .catch((error) => {
        if (active) {
          setUnavailable(true);
          onAvailabilityChange?.(false);
          onError(error instanceof Error ? error.message : 'Google sign-in is unavailable.');
        }
      });
    return () => {
      active = false;
      window.google?.accounts?.id.cancel();
    };
  }, [onAvailabilityChange, onCredential, onError]);

  return (
    <div className={`relative w-full ${disabled || working ? 'pointer-events-none opacity-60' : ''}`}>
      <div
        ref={containerRef}
        className={`min-h-11 w-full justify-center overflow-hidden ${enabled ? 'flex' : 'hidden'}`}
      />
      {unavailable && !enabled && (
        <div className="space-y-2">
          <button
            type="button"
            disabled
            className="flex h-11 w-full cursor-not-allowed items-center justify-center gap-3 rounded-md border border-[#242424] bg-[#101010] px-4 text-sm font-medium text-[#A1A1AA]"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5">
              <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.92h5.38a4.6 4.6 0 0 1-2 3.02v2.54h3.24c1.9-1.75 2.98-4.33 2.98-7.41Z" />
              <path fill="#34A853" d="M12 22c2.7 0 4.98-.9 6.64-2.36l-3.24-2.54c-.9.6-2.05.96-3.4.96-2.61 0-4.82-1.76-5.61-4.13H3.04v2.62A10 10 0 0 0 12 22Z" />
              <path fill="#FBBC05" d="M6.39 13.93A6.02 6.02 0 0 1 6.07 12c0-.67.12-1.32.32-1.93V7.45H3.04A10 10 0 0 0 2 12c0 1.63.39 3.17 1.04 4.55l3.35-2.62Z" />
              <path fill="#EA4335" d="M12 5.94c1.47 0 2.79.5 3.83 1.5l2.88-2.88A9.65 9.65 0 0 0 12 2a10 10 0 0 0-8.96 5.45l3.35 2.62C7.18 7.7 9.39 5.94 12 5.94Z" />
            </svg>
            Continue with Google
          </button>
          <p className="text-center text-xs text-[#71717A]">
            Google sign-in is temporarily unavailable.
          </p>
        </div>
      )}
      {working && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#101010]/80">
          <Loader2 className="h-4 w-4 animate-spin text-[#c16e43]" />
        </div>
      )}
    </div>
  );
}
