import { useState, useCallback } from 'react';
import type { Notification } from '@/types';

let idCounter = 0;

export function useToast() {
  const [toasts, setToasts] = useState<Notification[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const addToast = useCallback((type: Notification['type'], title: string, message: string) => {
    const id = `toast_${++idCounter}`;
    const toast: Notification = {
      id,
      type,
      title,
      message,
      timestamp: new Date().toISOString(),
      read: false,
    };
    setToasts(prev => [...prev, toast]);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      removeToast(id);
    }, 5000);

    return id;
  }, [removeToast]);

  const success = useCallback((title: string, message: string) => {
    return addToast('success', title, message);
  }, [addToast]);

  const error = useCallback((title: string, message: string) => {
    return addToast('error', title, message);
  }, [addToast]);

  const warning = useCallback((title: string, message: string) => {
    return addToast('warning', title, message);
  }, [addToast]);

  const info = useCallback((title: string, message: string) => {
    return addToast('info', title, message);
  }, [addToast]);

  return {
    toasts,
    addToast,
    removeToast,
    success,
    error,
    warning,
    info,
  };
}
