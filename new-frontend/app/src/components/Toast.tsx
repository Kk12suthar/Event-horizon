import { useEffect, useState } from 'react';
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import type { Notification } from '@/types';

interface ToastProps {
  notification: Notification;
  onDismiss: (id: string) => void;
}

const icons = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
};

const borderColors = {
  success: 'border-l-[#22C55E]',
  error: 'border-l-[#F97066]',
  warning: 'border-l-[#F59E0B]',
  info: 'border-l-[#E4E4E7]',
};

export function Toast({ notification, onDismiss }: ToastProps) {
  const [progress, setProgress] = useState(100);
  const Icon = icons[notification.type];

  useEffect(() => {
    const duration = 5000;
    const interval = 50;
    const step = 100 / (duration / interval);
    const timer = setInterval(() => {
      setProgress(prev => {
        if (prev <= 0) {
          clearInterval(timer);
          return 0;
        }
        return prev - step;
      });
    }, interval);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (progress <= 0) {
      onDismiss(notification.id);
    }
  }, [progress, notification.id, onDismiss]);

  return (
    <div className={`toast-enter relative flex items-start gap-3 w-full max-w-[400px] bg-[#101010] border border-[#242424] border-l-[3px] ${borderColors[notification.type]} rounded-xl p-4 shadow-[0_10px_40px_rgba(0,0,0,0.5)]`}>
      <Icon className="w-5 h-5 mt-0.5 flex-shrink-0" style={{
        color: notification.type === 'success' ? '#22C55E' :
               notification.type === 'error' ? '#F97066' :
               notification.type === 'warning' ? '#F59E0B' : '#E4E4E7'
      }} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-white">{notification.title}</p>
        <p className="text-xs text-[#A1A1AA] mt-0.5">{notification.message}</p>
      </div>
      <button
        onClick={() => onDismiss(notification.id)}
        className="flex-shrink-0 text-[#71717A] hover:text-white transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
      {/* Progress bar */}
      <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#242424] rounded-b-xl overflow-hidden">
        <div
          className="h-full transition-all duration-100 ease-linear"
          style={{
            width: `${progress}%`,
            backgroundColor: notification.type === 'success' ? '#22C55E' :
                            notification.type === 'error' ? '#F97066' :
                            notification.type === 'warning' ? '#F59E0B' : '#E4E4E7'
          }}
        />
      </div>
    </div>
  );
}

interface ToastContainerProps {
  toasts: Notification[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-3">
      {toasts.map(toast => (
        <Toast key={toast.id} notification={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
