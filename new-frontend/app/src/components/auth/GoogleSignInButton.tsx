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
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let active = true;
    const nonce = createNonce();
    void getGoogleSignInConfig()
      .then(async (config) => {
        if (!active) return;
        if (!config.enabled || !config.client_id) {
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
    <div className={`relative w-full ${!enabled ? 'max-h-0 overflow-hidden opacity-0' : ''} ${disabled || working ? 'pointer-events-none opacity-60' : ''}`}>
      <div ref={containerRef} className="flex min-h-11 w-full justify-center overflow-hidden" />
      {working && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#101010]/80">
          <Loader2 className="h-4 w-4 animate-spin text-[#c16e43]" />
        </div>
      )}
    </div>
  );
}
