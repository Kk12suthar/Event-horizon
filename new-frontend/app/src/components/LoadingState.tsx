interface LoadingStateProps {
  message?: string;
  fullPage?: boolean;
}

export function LoadingState({ message = 'Loading...', fullPage = false }: LoadingStateProps) {
  const content = (
    <div className="flex flex-col items-center justify-center gap-4">
      <div className="w-10 h-10 border-2 border-[#242424] border-t-[#E4E4E7] rounded-full animate-spin-slow" />
      <p className="text-sm text-[#A1A1AA]">{message}</p>
    </div>
  );

  if (fullPage) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        {content}
      </div>
    );
  }

  return content;
}

interface SkeletonProps {
  className?: string;
  count?: number;
}

export function Skeleton({ className = 'h-4 w-full', count = 1 }: SkeletonProps) {
  return (
    <div className="flex flex-col gap-2 w-full">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={`animate-shimmer rounded-md ${className}`} />
      ))}
    </div>
  );
}
