import { FolderOpen, FileX, Users, Shield, BarChart3, Upload } from 'lucide-react';

interface EmptyStateProps {
  icon?: 'folder' | 'file' | 'users' | 'shield' | 'chart' | 'upload';
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

const iconMap = {
  folder: FolderOpen,
  file: FileX,
  users: Users,
  shield: Shield,
  chart: BarChart3,
  upload: Upload,
};

export function EmptyState({ icon = 'folder', title, description, action }: EmptyStateProps) {
  const Icon = iconMap[icon];

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-16 h-16 rounded-xl bg-[#161616] border border-[#2A2A2A] flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-[#2A2A2A]" />
      </div>
      <h3 className="text-lg font-semibold text-[#71717A]">{title}</h3>
      {description && (
        <p className="text-sm text-[#71717A] mt-2 max-w-[400px]">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-6 px-4 py-2 bg-[#c16e43] text-[#0A0A0A] text-sm font-semibold rounded-lg hover:bg-[#d08a5e] transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
