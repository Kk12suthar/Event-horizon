import {
  FolderKanban,
  Sparkles,
  Shield,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  FolderOpen,
} from 'lucide-react';
import type { User, Folder, Project } from '@/types';

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  currentRoute: string;
  onNavigate: (route: string) => void;
  user: User | null;
  selectedFolder: Folder | null;
  selectedProject: Project | null;
}

// Minimal navigation surface (Requirement 1.1 / 1.2): only Projects and
// Workspace are global destinations here; Admin Panel is rendered separately
// below and only for the Admin role. Upload/Transform/Dashboard/Report are no
// longer navigation entries - they live inside the unified Workspace as modes.
const navItems = [
  { label: 'Projects', icon: FolderKanban, route: '/app/project', roles: ['Admin', 'Analyst', 'Viewer'] as const },
  { label: 'Workspace', icon: Sparkles, route: '/app/workspace', roles: ['Admin', 'Analyst', 'Viewer'] as const },
];

export function Sidebar({ isOpen, onToggle, currentRoute, onNavigate, user, selectedFolder, selectedProject }: SidebarProps) {
  const isActive = (route: string) => currentRoute === route || currentRoute.startsWith(route + '/');
  const userRole = user?.role;

  const canAccess = (roles: readonly string[]) => {
    if (!userRole) return false;
    return roles.includes(userRole);
  };

  return (
    <div className="flex flex-col h-full bg-[#0D0D0D] border-r border-[#262626]">
      {/* Logo */}
      <div className={`flex items-center h-14 px-4 border-b border-[#262626] ${!isOpen ? 'justify-center' : ''}`}>
        {isOpen ? (
          <>
            <span className="text-lg font-bold text-white tracking-tight">
              Event<span className="text-[#E4E4E7]">Horizon</span>
            </span>
            <button
              onClick={onToggle}
              className="ml-auto w-7 h-7 flex items-center justify-center rounded-lg text-[#8C8C8C] hover:text-white hover:bg-[#181818] transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </>
        ) : (
          <button
            onClick={onToggle}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-[#8C8C8C] hover:text-white hover:bg-[#181818] transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const hasAccess = canAccess(item.roles);
          const active = isActive(item.route);

          if (!hasAccess && item.route === '/app/admin-panel') return null;

          return (
            <button
              key={item.route}
              onClick={() => hasAccess && onNavigate(item.route)}
              disabled={!hasAccess}
              title={item.label}
              className={`
                w-full flex items-center gap-3 h-10 rounded-lg transition-all duration-200 relative
                ${isOpen ? 'px-3' : 'px-0 justify-center'}
                ${active
                  ? 'bg-[#181818] text-[#E4E4E7]'
                  : hasAccess
                    ? 'text-[#B8B8B8] hover:bg-[#181818] hover:text-white'
                    : 'text-[#B8B8B8]/40 cursor-not-allowed'
                }
              `}
            >
              {active && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 bg-[#c16e43] rounded-r" />
              )}
              <item.icon className="w-[18px] h-[18px] flex-shrink-0" />
              {isOpen && (
                <span className="text-xs font-medium uppercase tracking-[0.5px] truncate">
                  {item.label}
                </span>
              )}
            </button>
          );
        })}

        {/* Admin Panel - only for admins */}
        {userRole === 'Admin' && (
          <button
            onClick={() => onNavigate('/app/admin-panel')}
            className={`
              w-full flex items-center gap-3 h-10 rounded-lg transition-all duration-200 relative
              ${isOpen ? 'px-3' : 'px-0 justify-center'}
              ${isActive('/app/admin-panel')
                ? 'bg-[#181818] text-[#E4E4E7]'
                : 'text-[#B8B8B8] hover:bg-[#181818] hover:text-white'
              }
            `}
          >
            {isActive('/app/admin-panel') && (
              <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 bg-[#c16e43] rounded-r" />
            )}
            <Shield className="w-[18px] h-[18px] flex-shrink-0" />
            {isOpen && (
              <span className="text-xs font-medium uppercase tracking-[0.5px] truncate">
                Admin Panel
              </span>
            )}
          </button>
        )}

        {/* Active Folder Context */}
        {selectedFolder && isOpen && (
          <div className="mt-6 pt-4 border-t border-[#262626]">
            <p className="px-3 text-[10px] font-medium text-[#8C8C8C] uppercase tracking-wider mb-2">
              Active Folder
            </p>
            <div className="px-3 py-2 rounded-lg bg-[#181818]">
              <div className="flex items-center gap-2">
                <FolderOpen className="w-4 h-4 text-[#E4E4E7] flex-shrink-0" />
                <span className="text-sm font-semibold text-white truncate">
                  {selectedFolder.name}
                </span>
              </div>
              <p className="text-xs text-[#B8B8B8] mt-1 truncate">
                {selectedProject?.name}
              </p>
            </div>
          </div>
        )}
      </nav>

      {/* Bottom */}
      <div className={`px-3 py-3 border-t border-[#262626] ${!isOpen ? 'flex justify-center' : ''}`}>
        <button
          className={`flex items-center gap-2 text-[#8C8C8C] hover:text-white transition-colors ${!isOpen ? 'justify-center w-8 h-8' : 'px-3 h-9 w-full'}`}
        >
          <HelpCircle className="w-[18px] h-[18px] flex-shrink-0" />
          {isOpen && <span className="text-xs font-medium">Help</span>}
        </button>
      </div>
    </div>
  );
}
