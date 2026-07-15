import { WifiOff } from 'lucide-react';

interface OfflineStateProps {
  onRetry: () => void;
  fullPage?: boolean;
}

export function OfflineState({ onRetry, fullPage = true }: OfflineStateProps) {
  const content = (
    <div className="flex flex-col items-center justify-center gap-4 max-w-md mx-auto text-center">
      <div className="w-16 h-16 rounded-2xl bg-[#101010] border border-[#242424] flex items-center justify-center">
        <WifiOff className="w-8 h-8 text-[#F97066]" />
      </div>
      <h2 className="text-xl font-semibold text-white">Server unavailable</h2>
      <p className="text-sm text-[#A1A1AA]">
        Please check your connection and try again.
      </p>
      <button
        onClick={onRetry}
        className="px-6 py-2.5 bg-[#c16e43] text-[#0A0A0A] text-sm font-semibold rounded-lg hover:bg-[#d08a5e] transition-colors"
      >
        Retry Connection
      </button>
    </div>
  );

  if (fullPage) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        {content}
      </div>
    );
  }

  return (
    <div className="py-12">
      {content}
    </div>
  );
}
